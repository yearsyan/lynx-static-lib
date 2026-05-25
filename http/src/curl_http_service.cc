#include "lynxlib/http_service.h"

#include <curl/curl.h>

#include <algorithm>
#include <chrono>
#include <condition_variable>
#include <cctype>
#include <cstdint>
#include <cstring>
#include <deque>
#include <functional>
#include <list>
#include <limits>
#include <map>
#include <memory>
#include <mutex>
#include <new>
#include <string>
#include <thread>
#include <unordered_map>
#include <utility>
#include <vector>

#ifdef _WIN32
#include <winsock2.h>
#include <iphlpapi.h>
#else
#include <sys/select.h>
#include <sys/time.h>
#endif

#include "capi/lynx_http_service_capi.h"
#include "capi/lynx_generic_resource_fetcher_capi.h"
#include "capi/lynx_resource_request_capi.h"
#include "capi/lynx_resource_response_capi.h"
#include "capi/lynx_service_center_capi.h"
#include "lynx_http_service.h"

namespace lynxlib {
namespace http {
namespace {

constexpr auto kSelectWakeInterval = std::chrono::milliseconds(10);

void EnsureCurlGlobalInit() {
  static std::once_flag init_once;
  std::call_once(init_once, []() { curl_global_init(CURL_GLOBAL_DEFAULT); });
}

std::string Trim(std::string value) {
  const auto begin = value.find_first_not_of(" \t\r\n");
  if (begin == std::string::npos) {
    return {};
  }
  const auto end = value.find_last_not_of(" \t\r\n");
  return value.substr(begin, end - begin + 1);
}

std::string ToUpperAscii(std::string value) {
  std::transform(value.begin(), value.end(), value.begin(), [](unsigned char c) {
    return static_cast<char>(std::toupper(c));
  });
  return value;
}

bool EqualsIgnoreCase(const std::string& left, const char* right) {
  std::string normalized_right = right ? right : "";
  return ToUpperAscii(left) == ToUpperAscii(normalized_right);
}

#ifdef _WIN32
std::string GetWindowsDnsServers() {
  ULONG buffer_size = 0;
  if (GetNetworkParams(nullptr, &buffer_size) != ERROR_BUFFER_OVERFLOW ||
      buffer_size == 0) {
    return {};
  }

  std::vector<uint8_t> buffer(buffer_size);
  auto* fixed_info = reinterpret_cast<FIXED_INFO*>(buffer.data());
  if (GetNetworkParams(fixed_info, &buffer_size) != NO_ERROR) {
    return {};
  }

  std::string servers;
  for (IP_ADDR_STRING* entry = &fixed_info->DnsServerList; entry;
       entry = entry->Next) {
    const char* address = entry->IpAddress.String;
    if (!address || address[0] == '\0' || std::strcmp(address, "0.0.0.0") == 0) {
      continue;
    }
    if (!servers.empty()) {
      servers += ",";
    }
    servers += address;
  }
  return servers;
}
#endif

bool WantsRead(int action) {
  return action == CURL_POLL_IN || action == CURL_POLL_INOUT;
}

bool WantsWrite(int action) {
  return action == CURL_POLL_OUT || action == CURL_POLL_INOUT;
}

timeval ToTimeval(std::chrono::milliseconds timeout) {
  if (timeout.count() < 0) {
    timeout = std::chrono::milliseconds(0);
  }
  const auto micros = std::chrono::duration_cast<std::chrono::microseconds>(timeout);
  timeval tv;
  tv.tv_sec = static_cast<long>(micros.count() / 1000000);
  tv.tv_usec = static_cast<long>(micros.count() % 1000000);
  return tv;
}

bool CheckCurlCode(CURLcode code, const char* option_name, std::string* error) {
  if (code == CURLE_OK) {
    return true;
  }
  *error = std::string(option_name) + " failed: " + curl_easy_strerror(code);
  return false;
}

void FreeResponseBody(uint8_t* content, size_t, void*) {
  delete[] content;
}

void FreeResourceBody(uint8_t* content, size_t, void*) {
  delete[] content;
}

struct RequestResult {
  int error_code = 0;
  long status_code = 0;
  std::string status_text;
  std::unordered_map<std::string, std::string> headers;
  std::vector<uint8_t> body;
  std::string error_message;
};

using RequestCompletion = std::function<void(RequestResult&&)>;

void CompleteResourceError(lynx_resource_response_t* response,
                           const std::string& message) {
  if (!response) {
    return;
  }
  lynx_resource_response_set_code(response, -1);
  lynx_resource_response_set_error_message(response, message.c_str());
  lynx_resource_response_callback(response);
  lynx_resource_response_release(response);
}

void CompleteResourceData(lynx_resource_response_t* response,
                          const std::vector<uint8_t>& body) {
  if (!response) {
    return;
  }
  lynx_resource_response_set_code(response, 0);
  if (!body.empty()) {
    auto* bytes = new (std::nothrow) uint8_t[body.size()];
    if (!bytes) {
      CompleteResourceError(response, "out of memory while copying resource");
      return;
    }
    std::memcpy(bytes, body.data(), body.size());
    lynx_resource_response_set_data(response, bytes, body.size(),
                                    &FreeResourceBody, nullptr);
  }
  lynx_resource_response_callback(response);
  lynx_resource_response_release(response);
}

struct RequestJob {
  std::string url;
  std::string method;
  std::unordered_map<std::string, std::string> headers;
  std::vector<uint8_t> body;
  RequestCompletion complete;
};

void CompleteJob(std::unique_ptr<RequestJob> job, RequestResult result) {
  if (job && job->complete) {
    job->complete(std::move(result));
  }
}

void CompleteJobError(std::unique_ptr<RequestJob> job, int code,
                      const std::string& message) {
  RequestResult result;
  result.error_code = code;
  result.error_message = message;
  CompleteJob(std::move(job), std::move(result));
}

struct EasyContext {
  ~EasyContext() {
    if (request_headers) {
      curl_slist_free_all(request_headers);
    }
  }

  CURL* easy = nullptr;
  curl_slist* request_headers = nullptr;
  std::unique_ptr<RequestJob> job;
  std::vector<uint8_t> response_body;
  std::unordered_map<std::string, std::string> response_headers;
  std::string status_text;
  std::string dns_servers;
  size_t max_response_bytes = 0;
  char error_buffer[CURL_ERROR_SIZE] = {};
  bool response_too_large = false;
};

class CurlMultiSocketDispatcher {
 public:
  explicit CurlMultiSocketDispatcher(CurlHttpServiceOptions options)
      : options_(options) {
    EnsureCurlGlobalInit();
    multi_ = curl_multi_init();
    if (!multi_) {
      stopping_ = true;
      return;
    }
    curl_multi_setopt(multi_, CURLMOPT_SOCKETFUNCTION,
                      &CurlMultiSocketDispatcher::SocketCallback);
    curl_multi_setopt(multi_, CURLMOPT_SOCKETDATA, this);
    curl_multi_setopt(multi_, CURLMOPT_TIMERFUNCTION,
                      &CurlMultiSocketDispatcher::TimerCallback);
    curl_multi_setopt(multi_, CURLMOPT_TIMERDATA, this);
    worker_ = std::thread([this]() { Run(); });
  }

  ~CurlMultiSocketDispatcher() {
    {
      std::lock_guard<std::mutex> lock(mutex_);
      stopping_ = true;
    }
    cv_.notify_one();
    if (worker_.joinable()) {
      worker_.join();
    }
    if (multi_) {
      curl_multi_cleanup(multi_);
      multi_ = nullptr;
    }
  }

  void Submit(std::unique_ptr<RequestJob> job) {
    if (!job) {
      return;
    }

    bool rejected = false;
    {
      std::lock_guard<std::mutex> lock(mutex_);
      if (stopping_) {
        rejected = true;
      } else {
        pending_.push_back(std::move(job));
      }
    }
    if (rejected) {
      CompleteJobError(std::move(job), -1,
                       multi_ ? "http service is stopped"
                              : "curl_multi_init failed");
      return;
    }
    cv_.notify_one();
  }

 private:
  static size_t WriteCallback(char* contents, size_t size, size_t nmemb,
                              void* user_data) {
    auto* context = static_cast<EasyContext*>(user_data);
    if (nmemb != 0 && size > std::numeric_limits<size_t>::max() / nmemb) {
      context->response_too_large = true;
      return 0;
    }
    const size_t byte_count = size * nmemb;
    if (byte_count == 0) {
      return 0;
    }

    if (context->max_response_bytes > 0) {
      const size_t current = context->response_body.size();
      if (current > context->max_response_bytes ||
          byte_count > context->max_response_bytes - current) {
        context->response_too_large = true;
        return 0;
      }
    }
    const auto* bytes = reinterpret_cast<const uint8_t*>(contents);
    context->response_body.insert(context->response_body.end(), bytes,
                                  bytes + byte_count);
    return byte_count;
  }

  static size_t HeaderCallback(char* buffer, size_t size, size_t nitems,
                               void* user_data) {
    auto* context = static_cast<EasyContext*>(user_data);
    const size_t byte_count = size * nitems;
    if (byte_count == 0) {
      return 0;
    }

    std::string line(buffer, byte_count);
    line = Trim(std::move(line));
    if (line.empty()) {
      return byte_count;
    }

    if (line.rfind("HTTP/", 0) == 0) {
      context->response_headers.clear();
      context->status_text.clear();
      const auto first_space = line.find(' ');
      if (first_space != std::string::npos) {
        const auto second_space = line.find(' ', first_space + 1);
        if (second_space != std::string::npos) {
          context->status_text = Trim(line.substr(second_space + 1));
        }
      }
      return byte_count;
    }

    const auto colon = line.find(':');
    if (colon == std::string::npos) {
      return byte_count;
    }
    std::string key = Trim(line.substr(0, colon));
    std::string value = Trim(line.substr(colon + 1));
    if (!key.empty()) {
      context->response_headers[std::move(key)] = std::move(value);
    }
    return byte_count;
  }

  static int SocketCallback(CURL*, curl_socket_t socket, int what,
                            void* user_data, void*) {
    auto* dispatcher = static_cast<CurlMultiSocketDispatcher*>(user_data);
    dispatcher->UpdateSocket(socket, what);
    return 0;
  }

  static int TimerCallback(CURLM*, long timeout_ms, void* user_data) {
    auto* dispatcher = static_cast<CurlMultiSocketDispatcher*>(user_data);
    dispatcher->UpdateTimer(timeout_ms);
    return 0;
  }

  void Run() {
    if (!multi_) {
      FailPendingJobs("curl_multi_init failed");
      return;
    }

    for (;;) {
      DrainPendingJobs();
      if (IsStopping()) {
        break;
      }

      if (active_.empty()) {
        WaitForNewWork();
        continue;
      }

      if (IsTimerExpired()) {
        TriggerTimeout();
        DrainCompleted();
        continue;
      }

      if (socket_actions_.empty()) {
        if (WaitForControlEvent(ComputePollTimeout())) {
          continue;
        }
        if (IsTimerExpired()) {
          TriggerTimeout();
          DrainCompleted();
        }
        continue;
      }

      PollSockets(ComputePollTimeout());
      DrainCompleted();
    }

    FailPendingJobs("http service is stopped");
    FailActiveJobs("http service is stopped");
  }

  bool IsStopping() {
    std::lock_guard<std::mutex> lock(mutex_);
    return stopping_;
  }

  void WaitForNewWork() {
    std::unique_lock<std::mutex> lock(mutex_);
    cv_.wait(lock, [this]() { return stopping_ || !pending_.empty(); });
  }

  bool WaitForControlEvent(std::chrono::milliseconds timeout) {
    std::unique_lock<std::mutex> lock(mutex_);
    return cv_.wait_for(lock, timeout,
                        [this]() { return stopping_ || !pending_.empty(); });
  }

  void DrainPendingJobs() {
    std::deque<std::unique_ptr<RequestJob>> jobs;
    {
      std::lock_guard<std::mutex> lock(mutex_);
      jobs.swap(pending_);
    }

    for (auto& job : jobs) {
      StartTransfer(std::move(job));
    }
  }

  void StartTransfer(std::unique_ptr<RequestJob> job) {
    auto context = std::make_unique<EasyContext>();
    context->job = std::move(job);
    context->max_response_bytes = options_.max_response_bytes;
    context->easy = curl_easy_init();
    if (!context->easy) {
      CompleteJobError(std::move(context->job), -1, "curl_easy_init failed");
      return;
    }

    CURL* easy = context->easy;
    std::string setup_error;
    if (!ConfigureEasyHandle(context.get(), &setup_error)) {
      curl_easy_cleanup(easy);
      context->easy = nullptr;
      CompleteJobError(std::move(context->job), -1, setup_error);
      return;
    }

    CURLMcode add_result = curl_multi_add_handle(multi_, easy);
    if (add_result != CURLM_OK) {
      curl_easy_cleanup(easy);
      context->easy = nullptr;
      CompleteJobError(std::move(context->job), -1,
                       curl_multi_strerror(add_result));
      return;
    }

    active_[easy] = std::move(context);
    TriggerTimeout();
    DrainCompleted();
  }

  bool ConfigureEasyHandle(EasyContext* context, std::string* setup_error) {
    CURL* easy = context->easy;
    RequestJob* job = context->job.get();

    if (!CheckCurlCode(curl_easy_setopt(easy, CURLOPT_URL, job->url.c_str()),
                       "CURLOPT_URL", setup_error) ||
        !CheckCurlCode(curl_easy_setopt(easy, CURLOPT_PRIVATE, context),
                       "CURLOPT_PRIVATE", setup_error) ||
        !CheckCurlCode(curl_easy_setopt(easy, CURLOPT_WRITEDATA, context),
                       "CURLOPT_WRITEDATA", setup_error) ||
        !CheckCurlCode(curl_easy_setopt(easy, CURLOPT_WRITEFUNCTION,
                                        &CurlMultiSocketDispatcher::WriteCallback),
                       "CURLOPT_WRITEFUNCTION", setup_error) ||
        !CheckCurlCode(curl_easy_setopt(easy, CURLOPT_HEADERDATA, context),
                       "CURLOPT_HEADERDATA", setup_error) ||
        !CheckCurlCode(curl_easy_setopt(easy, CURLOPT_HEADERFUNCTION,
                                        &CurlMultiSocketDispatcher::HeaderCallback),
                       "CURLOPT_HEADERFUNCTION", setup_error) ||
        !CheckCurlCode(curl_easy_setopt(easy, CURLOPT_ERRORBUFFER,
                                        context->error_buffer),
                       "CURLOPT_ERRORBUFFER", setup_error) ||
        !CheckCurlCode(curl_easy_setopt(easy, CURLOPT_NOSIGNAL, 1L),
                       "CURLOPT_NOSIGNAL", setup_error) ||
        !CheckCurlCode(curl_easy_setopt(easy, CURLOPT_PROTOCOLS_STR,
                                        "http,https"),
                       "CURLOPT_PROTOCOLS_STR", setup_error) ||
        !CheckCurlCode(curl_easy_setopt(easy, CURLOPT_REDIR_PROTOCOLS_STR,
                                        "http,https"),
                       "CURLOPT_REDIR_PROTOCOLS_STR", setup_error) ||
        !CheckCurlCode(curl_easy_setopt(easy, CURLOPT_FOLLOWLOCATION,
                                        options_.follow_redirects ? 1L : 0L),
                       "CURLOPT_FOLLOWLOCATION", setup_error) ||
        !CheckCurlCode(curl_easy_setopt(easy, CURLOPT_MAXREDIRS,
                                        options_.max_redirects),
                       "CURLOPT_MAXREDIRS", setup_error) ||
        !CheckCurlCode(curl_easy_setopt(easy, CURLOPT_VERBOSE,
                                        options_.verbose ? 1L : 0L),
                       "CURLOPT_VERBOSE", setup_error) ||
        !CheckCurlCode(curl_easy_setopt(easy, CURLOPT_ACCEPT_ENCODING, ""),
                       "CURLOPT_ACCEPT_ENCODING", setup_error)) {
      return false;
    }

#ifdef _WIN32
    context->dns_servers = GetWindowsDnsServers();
    if (!context->dns_servers.empty()) {
      (void)curl_easy_setopt(easy, CURLOPT_DNS_SERVERS,
                             context->dns_servers.c_str());
    }
#endif

    if (options_.connect_timeout_ms > 0 &&
        !CheckCurlCode(curl_easy_setopt(easy, CURLOPT_CONNECTTIMEOUT_MS,
                                        options_.connect_timeout_ms),
                       "CURLOPT_CONNECTTIMEOUT_MS", setup_error)) {
      return false;
    }
    if (options_.request_timeout_ms > 0 &&
        !CheckCurlCode(curl_easy_setopt(easy, CURLOPT_TIMEOUT_MS,
                                        options_.request_timeout_ms),
                       "CURLOPT_TIMEOUT_MS", setup_error)) {
      return false;
    }

    if (!ConfigureHeaders(context, setup_error)) {
      return false;
    }
    return ConfigureMethodAndBody(context, setup_error);
  }

  bool ConfigureHeaders(EasyContext* context, std::string* setup_error) {
    bool has_expect_header = false;
    for (const auto& header : context->job->headers) {
      if (header.first.empty()) {
        continue;
      }
      has_expect_header = has_expect_header || EqualsIgnoreCase(header.first, "Expect");
      const std::string line = header.first + ": " + header.second;
      curl_slist* next = curl_slist_append(context->request_headers, line.c_str());
      if (!next) {
        *setup_error = "curl_slist_append failed";
        return false;
      }
      context->request_headers = next;
    }

    if (!context->job->body.empty() && !has_expect_header) {
      curl_slist* next = curl_slist_append(context->request_headers, "Expect:");
      if (!next) {
        *setup_error = "curl_slist_append failed";
        return false;
      }
      context->request_headers = next;
    }

    if (context->request_headers &&
        !CheckCurlCode(curl_easy_setopt(context->easy, CURLOPT_HTTPHEADER,
                                        context->request_headers),
                       "CURLOPT_HTTPHEADER", setup_error)) {
      return false;
    }
    return true;
  }

  bool ConfigureMethodAndBody(EasyContext* context, std::string* setup_error) {
    RequestJob* job = context->job.get();
    std::string method = ToUpperAscii(job->method.empty() ? "GET" : job->method);
    CURL* easy = context->easy;

    if (method == "HEAD") {
      return CheckCurlCode(curl_easy_setopt(easy, CURLOPT_NOBODY, 1L),
                           "CURLOPT_NOBODY", setup_error);
    }

    if (method == "GET" && job->body.empty()) {
      return true;
    }

    if (method == "POST") {
      if (!CheckCurlCode(curl_easy_setopt(easy, CURLOPT_POST, 1L),
                         "CURLOPT_POST", setup_error)) {
        return false;
      }
    } else {
      if (!CheckCurlCode(curl_easy_setopt(easy, CURLOPT_CUSTOMREQUEST,
                                          method.c_str()),
                         "CURLOPT_CUSTOMREQUEST", setup_error)) {
        return false;
      }
    }

    if (!job->body.empty() || method == "POST") {
      const char* body_data =
          job->body.empty() ? "" : reinterpret_cast<const char*>(job->body.data());
      if (!CheckCurlCode(curl_easy_setopt(easy, CURLOPT_POSTFIELDSIZE_LARGE,
                                          static_cast<curl_off_t>(job->body.size())),
                         "CURLOPT_POSTFIELDSIZE_LARGE", setup_error) ||
          !CheckCurlCode(curl_easy_setopt(easy, CURLOPT_POSTFIELDS, body_data),
                         "CURLOPT_POSTFIELDS", setup_error)) {
        return false;
      }
    }
    return true;
  }

  void UpdateSocket(curl_socket_t socket, int what) {
    if (what == CURL_POLL_REMOVE) {
      socket_actions_.erase(socket);
      return;
    }
    socket_actions_[socket] = what;
  }

  void UpdateTimer(long timeout_ms) {
    if (timeout_ms < 0) {
      has_timeout_ = false;
      return;
    }
    has_timeout_ = true;
    timeout_deadline_ = std::chrono::steady_clock::now() +
                        std::chrono::milliseconds(timeout_ms);
  }

  bool IsTimerExpired() const {
    return has_timeout_ && std::chrono::steady_clock::now() >= timeout_deadline_;
  }

  std::chrono::milliseconds ComputePollTimeout() const {
    auto timeout = kSelectWakeInterval;
    if (has_timeout_) {
      const auto now = std::chrono::steady_clock::now();
      if (timeout_deadline_ <= now) {
        return std::chrono::milliseconds(0);
      }
      const auto remaining =
          std::chrono::duration_cast<std::chrono::milliseconds>(timeout_deadline_ - now);
      timeout = std::min(timeout, std::max(std::chrono::milliseconds(1), remaining));
    }
    return timeout;
  }

  void TriggerTimeout() {
    int running_handles = 0;
    curl_multi_socket_action(multi_, CURL_SOCKET_TIMEOUT, 0, &running_handles);
  }

  void PollSockets(std::chrono::milliseconds timeout) {
    fd_set read_fds;
    fd_set write_fds;
    fd_set error_fds;
    FD_ZERO(&read_fds);
    FD_ZERO(&write_fds);
    FD_ZERO(&error_fds);

    curl_socket_t max_socket = 0;
    std::vector<curl_socket_t> sockets;
    sockets.reserve(socket_actions_.size());
    for (const auto& entry : socket_actions_) {
      const curl_socket_t socket = entry.first;
      const int action = entry.second;
      sockets.push_back(socket);
      if (WantsRead(action)) {
        FD_SET(socket, &read_fds);
      }
      if (WantsWrite(action)) {
        FD_SET(socket, &write_fds);
      }
      FD_SET(socket, &error_fds);
      max_socket = std::max(max_socket, socket);
    }

    timeval tv = ToTimeval(timeout);
    const int result = select(static_cast<int>(max_socket + 1), &read_fds,
                              &write_fds, &error_fds, &tv);
    if (result <= 0) {
      if (IsTimerExpired()) {
        TriggerTimeout();
      }
      return;
    }

    for (curl_socket_t socket : sockets) {
      if (socket_actions_.find(socket) == socket_actions_.end()) {
        continue;
      }

      int flags = 0;
      if (FD_ISSET(socket, &read_fds)) {
        flags |= CURL_CSELECT_IN;
      }
      if (FD_ISSET(socket, &write_fds)) {
        flags |= CURL_CSELECT_OUT;
      }
      if (FD_ISSET(socket, &error_fds)) {
        flags |= CURL_CSELECT_ERR;
      }
      if (flags != 0) {
        int running_handles = 0;
        curl_multi_socket_action(multi_, socket, flags, &running_handles);
      }
    }
  }

  void DrainCompleted() {
    int messages_left = 0;
    while (CURLMsg* message = curl_multi_info_read(multi_, &messages_left)) {
      if (message->msg != CURLMSG_DONE) {
        continue;
      }

      CURL* easy = message->easy_handle;
      auto it = active_.find(easy);
      if (it == active_.end()) {
        curl_multi_remove_handle(multi_, easy);
        curl_easy_cleanup(easy);
        continue;
      }

      auto context = std::move(it->second);
      active_.erase(it);

      long response_code = 0;
      curl_easy_getinfo(easy, CURLINFO_RESPONSE_CODE, &response_code);
      curl_multi_remove_handle(multi_, easy);
      curl_easy_cleanup(easy);
      context->easy = nullptr;

      CompleteTransfer(std::move(context), message->data.result, response_code);
    }
  }

  void CompleteTransfer(std::unique_ptr<EasyContext> context, CURLcode result,
                        long response_code) {
    if (context->response_too_large) {
      CompleteJobError(std::move(context->job),
                       -static_cast<int>(CURLE_WRITE_ERROR),
                       "response body exceeds max_response_bytes");
      return;
    }

    if (result != CURLE_OK) {
      std::string message = context->error_buffer[0]
                                ? context->error_buffer
                                : curl_easy_strerror(result);
      CompleteJobError(std::move(context->job), -static_cast<int>(result),
                       message);
      return;
    }

    RequestResult request_result;
    request_result.status_code = response_code;
    request_result.status_text = std::move(context->status_text);
    request_result.headers = std::move(context->response_headers);
    request_result.body = std::move(context->response_body);
    CompleteJob(std::move(context->job), std::move(request_result));
  }

  void FailPendingJobs(const std::string& message) {
    std::deque<std::unique_ptr<RequestJob>> jobs;
    {
      std::lock_guard<std::mutex> lock(mutex_);
      jobs.swap(pending_);
    }
    for (auto& job : jobs) {
      CompleteJobError(std::move(job), -1, message);
    }
  }

  void FailActiveJobs(const std::string& message) {
    for (auto& entry : active_) {
      CURL* easy = entry.first;
      auto& context = entry.second;
      curl_multi_remove_handle(multi_, easy);
      curl_easy_cleanup(easy);
      context->easy = nullptr;
      CompleteJobError(std::move(context->job), -1, message);
    }
    active_.clear();
    socket_actions_.clear();
  }

  CurlHttpServiceOptions options_;
  CURLM* multi_ = nullptr;
  std::thread worker_;
  std::mutex mutex_;
  std::condition_variable cv_;
  std::deque<std::unique_ptr<RequestJob>> pending_;
  bool stopping_ = false;

  std::map<curl_socket_t, int> socket_actions_;
  std::unordered_map<CURL*, std::unique_ptr<EasyContext>> active_;
  bool has_timeout_ = false;
  std::chrono::steady_clock::time_point timeout_deadline_;
};

class CurlHttpService final : public lynx::pub::LynxHttpService {
 public:
  explicit CurlHttpService(CurlHttpServiceOptions options)
      : dispatcher_(std::make_shared<CurlMultiSocketDispatcher>(options)) {}

  void Request(std::shared_ptr<lynx::pub::LynxHttpRequest> request,
               std::shared_ptr<lynx::pub::LynxHttpResponse> response) override {
    if (!request || !response) {
      return;
    }

    auto job = std::make_unique<RequestJob>();
    job->url = request->GetUrl();
    job->method = request->GetMethod();
    job->headers = request->GetHeaders();
    job->body = request->GetBody();
    job->complete =
        [response = std::move(response)](RequestResult&& result) {
          if (!response) {
            return;
          }
          if (result.error_code != 0) {
            response->SetStatusCode(result.error_code);
            response->SetStatusText(result.error_message.c_str());
            response->Complete();
            return;
          }

          response->SetStatusCode(static_cast<int>(result.status_code));
          response->SetStatusText(result.status_text.c_str());
          for (const auto& header : result.headers) {
            response->AddHeader(header.first, header.second);
          }
          if (!result.body.empty()) {
            const size_t length = result.body.size();
            auto* body = new (std::nothrow) uint8_t[length];
            if (!body) {
              response->SetStatusCode(-1);
              response->SetStatusText(
                  "out of memory while copying response body");
              response->Complete();
              return;
            }
            std::memcpy(body, result.body.data(), length);
            response->SetBody(body, length, FreeResponseBody, nullptr);
          }
          response->Complete();
        };
    dispatcher_->Submit(std::move(job));
  }

  std::shared_ptr<CurlMultiSocketDispatcher> dispatcher() const {
    return dispatcher_;
  }

 private:
  std::shared_ptr<CurlMultiSocketDispatcher> dispatcher_;
};

bool IsHttpUrl(const std::string& url) {
  return url.rfind("http://", 0) == 0 || url.rfind("https://", 0) == 0;
}

class ResourceFetcherState {
 public:
  ResourceFetcherState(std::shared_ptr<CurlMultiSocketDispatcher> dispatcher,
                       ResourceCacheOptions cache_options)
      : dispatcher_(std::move(dispatcher)),
        cache_options_(std::move(cache_options)) {}

  void Fetch(std::shared_ptr<ResourceFetcherState> self,
             lynx_resource_request_t* request,
             lynx_resource_response_t* response) {
    const char* raw_url = request ? lynx_resource_request_get_url(request) : nullptr;
    std::string url = raw_url ? raw_url : "";
    if (request) {
      lynx_resource_request_release(request);
    }

    if (!response) {
      return;
    }
    if (!IsHttpUrl(url)) {
      CompleteResourceError(response,
                            "only http and https resources are supported");
      return;
    }

    std::vector<uint8_t> cached_body;
    if (TryGetCachedBody(url, &cached_body)) {
      CompleteResourceData(response, cached_body);
      return;
    }

    if (!dispatcher_) {
      CompleteResourceError(response, "resource fetcher is not initialized");
      return;
    }

    auto job = std::make_unique<RequestJob>();
    job->url = url;
    job->method = "GET";
    job->complete =
        [self = std::move(self), url = std::move(url), response](
            RequestResult&& result) {
          if (result.error_code != 0) {
            CompleteResourceError(
                response, result.error_message.empty() ? "resource fetch failed"
                                                       : result.error_message);
            return;
          }

          if (result.status_code >= 400) {
            CompleteResourceError(
                response, "HTTP " + std::to_string(result.status_code));
            return;
          }

          if (self) {
            self->PutCachedBody(url, result.body);
          }
          CompleteResourceData(response, result.body);
        };
    dispatcher_->Submit(std::move(job));
  }

 private:
  struct CacheEntry {
    std::vector<uint8_t> body;
    std::chrono::steady_clock::time_point expires_at;
    std::list<std::string>::iterator lru;
  };

  bool CacheEnabled() const {
    return cache_options_.policy == ResourceCachePolicy::kMemory &&
           cache_options_.max_entries > 0 && cache_options_.max_bytes > 0;
  }

  bool IsExpired(const CacheEntry& entry,
                 std::chrono::steady_clock::time_point now) const {
    return entry.expires_at != std::chrono::steady_clock::time_point::max() &&
           now >= entry.expires_at;
  }

  bool TryGetCachedBody(const std::string& url, std::vector<uint8_t>* body) {
    if (!CacheEnabled()) {
      return false;
    }

    std::lock_guard<std::mutex> lock(cache_mutex_);
    auto it = cache_.find(url);
    if (it == cache_.end()) {
      return false;
    }

    const auto now = std::chrono::steady_clock::now();
    if (IsExpired(it->second, now)) {
      EraseCacheEntry(it);
      return false;
    }

    cache_lru_.splice(cache_lru_.begin(), cache_lru_, it->second.lru);
    *body = it->second.body;
    return true;
  }

  void PutCachedBody(const std::string& url, const std::vector<uint8_t>& body) {
    if (!CacheEnabled() || url.empty() || body.empty() ||
        body.size() > cache_options_.max_bytes) {
      return;
    }

    std::lock_guard<std::mutex> lock(cache_mutex_);
    auto existing = cache_.find(url);
    if (existing != cache_.end()) {
      EraseCacheEntry(existing);
    }

    while (!cache_.empty() &&
           (cache_.size() >= cache_options_.max_entries ||
            cache_bytes_ + body.size() > cache_options_.max_bytes)) {
      auto lru_url = cache_lru_.back();
      auto it = cache_.find(lru_url);
      if (it == cache_.end()) {
        cache_lru_.pop_back();
      } else {
        EraseCacheEntry(it);
      }
    }

    CacheEntry entry;
    entry.body = body;
    entry.expires_at = std::chrono::steady_clock::time_point::max();
    if (cache_options_.ttl_ms > 0) {
      entry.expires_at = std::chrono::steady_clock::now() +
                         std::chrono::milliseconds(cache_options_.ttl_ms);
    }
    cache_lru_.push_front(url);
    entry.lru = cache_lru_.begin();
    cache_bytes_ += entry.body.size();
    cache_.emplace(url, std::move(entry));
  }

  void EraseCacheEntry(
      std::unordered_map<std::string, CacheEntry>::iterator it) {
    cache_bytes_ -= it->second.body.size();
    cache_lru_.erase(it->second.lru);
    cache_.erase(it);
  }

  std::shared_ptr<CurlMultiSocketDispatcher> dispatcher_;
  ResourceCacheOptions cache_options_;
  std::mutex cache_mutex_;
  std::unordered_map<std::string, CacheEntry> cache_;
  std::list<std::string> cache_lru_;
  std::size_t cache_bytes_ = 0;
};

using ResourceFetcherStateHolder = std::shared_ptr<ResourceFetcherState>;

void ResourceFetcherFinalizer(lynx_generic_resource_fetcher_t*, void* user_data) {
  delete static_cast<ResourceFetcherStateHolder*>(user_data);
}

void ResourceFetcherFetchResource(lynx_generic_resource_fetcher_t* fetcher,
                                  lynx_resource_request_t* request,
                                  lynx_resource_response_t* response) {
  auto* holder = fetcher ? static_cast<ResourceFetcherStateHolder*>(
                              lynx_generic_resource_fetcher_get_user_data(fetcher))
                         : nullptr;
  ResourceFetcherStateHolder state = holder ? *holder : nullptr;
  if (!state) {
    if (request) {
      lynx_resource_request_release(request);
    }
    CompleteResourceError(response, "resource fetcher is not initialized");
    return;
  }
  state->Fetch(state, request, response);
}

std::mutex g_service_mutex;
std::shared_ptr<CurlHttpService> g_service;

void ReleaseServiceRegistration(const std::shared_ptr<CurlHttpService>& service) {
  if (!service || !service->Impl()) {
    return;
  }

  auto* http_service =
      reinterpret_cast<lynx_http_service_t*>(service->Impl());
  lynx_service_unregister_service(lynx_service_get_center_instance(),
                                  kServiceTypeHttp, http_service);
  lynx_http_service_release(http_service);
}

std::shared_ptr<CurlMultiSocketDispatcher> ResolveResourceDispatcher(
    const CurlGenericResourceFetcherOptions& options) {
  if (options.share_registered_http_service) {
    std::lock_guard<std::mutex> lock(g_service_mutex);
    if (g_service) {
      return g_service->dispatcher();
    }
  }
  return std::make_shared<CurlMultiSocketDispatcher>(options.http);
}

}  // namespace

void RegisterCurlHttpService(const CurlHttpServiceOptions& options) {
  auto service = std::make_shared<CurlHttpService>(options);
  service->InitIfNeeded();

  std::shared_ptr<CurlHttpService> old_service;
  {
    std::lock_guard<std::mutex> lock(g_service_mutex);
    lynx_service_register_service(lynx_service_get_center_instance(),
                                  kServiceTypeHttp, service->Impl());
    old_service = std::exchange(g_service, std::move(service));
  }
  ReleaseServiceRegistration(old_service);
}

void UnregisterCurlHttpService() {
  std::shared_ptr<CurlHttpService> service;
  {
    std::lock_guard<std::mutex> lock(g_service_mutex);
    service = g_service;
    g_service.reset();
  }
  ReleaseServiceRegistration(service);
}

lynx_generic_resource_fetcher_t* CreateCurlGenericResourceFetcher(
    const CurlGenericResourceFetcherOptions& options) {
  auto dispatcher = ResolveResourceDispatcher(options);
  auto state = std::make_shared<ResourceFetcherState>(std::move(dispatcher),
                                                     options.cache);
  auto* holder = new (std::nothrow) ResourceFetcherStateHolder(std::move(state));
  if (!holder) {
    return nullptr;
  }

  lynx_generic_resource_fetcher_t* fetcher =
      lynx_generic_resource_fetcher_create_with_finalizer(
          holder, &ResourceFetcherFinalizer);
  if (!fetcher) {
    delete holder;
    return nullptr;
  }
  lynx_generic_resource_fetcher_bind_fetch_resource(
      fetcher, &ResourceFetcherFetchResource);
  lynx_generic_resource_fetcher_bind_fetch_resource_path(
      fetcher, &ResourceFetcherFetchResource);
  return fetcher;
}

void ReleaseCurlGenericResourceFetcher(
    lynx_generic_resource_fetcher_t* fetcher) {
  if (fetcher) {
    lynx_generic_resource_fetcher_release(fetcher);
  }
}

}  // namespace http
}  // namespace lynxlib

extern "C" void lynxlib_http_register_default_service() {
  lynxlib::http::RegisterCurlHttpService();
}

extern "C" void lynxlib_http_unregister_service() {
  lynxlib::http::UnregisterCurlHttpService();
}

extern "C" lynx_generic_resource_fetcher_t*
lynxlib_http_create_default_generic_resource_fetcher() {
  return lynxlib::http::CreateCurlGenericResourceFetcher();
}

extern "C" lynx_generic_resource_fetcher_t*
lynxlib_http_create_memory_cached_generic_resource_fetcher(
    std::size_t max_entries, std::size_t max_bytes, long ttl_ms) {
  lynxlib::http::CurlGenericResourceFetcherOptions options;
  options.cache.policy = lynxlib::http::ResourceCachePolicy::kMemory;
  options.cache.max_entries = max_entries;
  options.cache.max_bytes = max_bytes;
  options.cache.ttl_ms = ttl_ms;
  return lynxlib::http::CreateCurlGenericResourceFetcher(options);
}

extern "C" void lynxlib_http_release_generic_resource_fetcher(
    lynx_generic_resource_fetcher_t* fetcher) {
  lynxlib::http::ReleaseCurlGenericResourceFetcher(fetcher);
}
