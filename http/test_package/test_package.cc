#include "lynxlib/http_service.h"

#include <winsock2.h>
#include <ws2tcpip.h>

#include <chrono>
#include <condition_variable>
#include <cstdint>
#include <cstring>
#include <functional>
#include <map>
#include <mutex>
#include <stdexcept>
#include <string>
#include <thread>
#include <vector>

struct lynx_http_request_t;
struct lynx_http_response_t;
struct lynx_http_service_t;
struct lynx_resource_request_t;
struct lynx_resource_response_t;
struct lynx_service_center_t;

enum lynx_service_type_e {
  kServiceTypeHttp = 1,
  kServiceTypeSecurity,
  kServiceTypeEventReporter,
};

using HttpResponseCallback = std::function<void(lynx_http_response_t*)>;

struct ResourceCallbackState {
  std::mutex* mutex = nullptr;
  std::condition_variable* cv = nullptr;
  bool* done = nullptr;
  int* status_code = nullptr;
  std::string* body = nullptr;
};

struct lynx_http_response_t {
  std::string url;
  int status_code = -1;
  std::string status_text;
  std::map<std::string, std::string> headers;

  struct body {
    uint8_t* content = nullptr;
    size_t length = 0;
    void (*dtor)(uint8_t*, size_t, void*) = nullptr;
    void* opaque = nullptr;
  } body;

  HttpResponseCallback callback = nullptr;
  bool completed = false;
};

lynx_http_request_t* lynx_http_request_create(const std::string& url);
lynx_http_response_t* lynx_http_response_create(HttpResponseCallback callback);

extern "C" {
lynx_service_center_t* lynx_service_get_center_instance();
void* lynx_service_get_service(lynx_service_center_t*, lynx_service_type_e type);
lynx_resource_request_t* lynx_resource_request_create(const char* url,
                                                      int type);
lynx_resource_response_t* lynx_resource_response_create(
    void (*callback)(lynx_resource_response_t*, void*), void* user_data);
void lynx_generic_resource_fetcher_fetch_resource(
    lynx_generic_resource_fetcher_t*, lynx_resource_request_t*,
    lynx_resource_response_t*);
int lynx_resource_response_get_code(lynx_resource_response_t* response);
const uint8_t* lynx_resource_response_get_data(
    lynx_resource_response_t* response);
size_t lynx_resource_response_get_data_length(
    lynx_resource_response_t* response);
}

void lynx_http_service_request(lynx_http_service_t* http_service,
                               lynx_http_request_t* request,
                               lynx_http_response_t* response);

namespace {

class WinsockSession {
 public:
  WinsockSession() {
    WSADATA data = {};
    if (WSAStartup(MAKEWORD(2, 2), &data) != 0) {
      throw std::runtime_error("WSAStartup failed");
    }
  }

  ~WinsockSession() { WSACleanup(); }
};

class LoopbackHttpServer {
 public:
  LoopbackHttpServer() {
    socket_ = socket(AF_INET, SOCK_STREAM, IPPROTO_TCP);
    if (socket_ == INVALID_SOCKET) {
      throw std::runtime_error("socket failed");
    }

    sockaddr_in address = {};
    address.sin_family = AF_INET;
    address.sin_addr.s_addr = htonl(INADDR_LOOPBACK);
    address.sin_port = 0;
    if (bind(socket_, reinterpret_cast<sockaddr*>(&address), sizeof(address)) !=
        0) {
      closesocket(socket_);
      throw std::runtime_error("bind failed");
    }
    if (listen(socket_, 1) != 0) {
      closesocket(socket_);
      throw std::runtime_error("listen failed");
    }

    int length = sizeof(address);
    if (getsockname(socket_, reinterpret_cast<sockaddr*>(&address), &length) !=
        0) {
      closesocket(socket_);
      throw std::runtime_error("getsockname failed");
    }
    port_ = ntohs(address.sin_port);
    thread_ = std::thread([this]() { ServeOneRequest(); });
  }

  ~LoopbackHttpServer() {
    if (socket_ != INVALID_SOCKET) {
      closesocket(socket_);
    }
    if (thread_.joinable()) {
      thread_.join();
    }
  }

  std::string url() const {
    return "http://127.0.0.1:" + std::to_string(port_) + "/lynxlib-http";
  }

 private:
  void ServeOneRequest() {
    SOCKET client = accept(socket_, nullptr, nullptr);
    if (client == INVALID_SOCKET) {
      return;
    }

    char buffer[1024] = {};
    recv(client, buffer, sizeof(buffer), 0);

    constexpr char kBody[] = "{\"ok\":true,\"source\":\"lynxlib-http\"}";
    const std::string response =
        "HTTP/1.1 200 OK\r\n"
        "Content-Type: application/json\r\n"
        "Content-Length: " +
        std::to_string(std::strlen(kBody)) +
        "\r\n"
        "Connection: close\r\n"
        "\r\n" +
        kBody;
    send(client, response.c_str(), static_cast<int>(response.size()), 0);
    shutdown(client, SD_BOTH);
    closesocket(client);
  }

  SOCKET socket_ = INVALID_SOCKET;
  uint16_t port_ = 0;
  std::thread thread_;
};

}  // namespace

int main() {
  WinsockSession winsock;
  LoopbackHttpServer service_server;
  LoopbackHttpServer resource_server;

  std::mutex mutex;
  std::condition_variable cv;
  bool done = false;
  int status_code = 0;
  std::string body;

  lynxlib::http::RegisterCurlHttpService();
  auto* service = reinterpret_cast<lynx_http_service_t*>(
      lynx_service_get_service(lynx_service_get_center_instance(),
                               kServiceTypeHttp));
  if (!service) {
    return 1;
  }

  lynx_http_request_t* request =
      lynx_http_request_create(service_server.url());
  lynx_http_response_t* response =
      lynx_http_response_create([&](lynx_http_response_t* response) {
        std::lock_guard<std::mutex> lock(mutex);
        status_code = response->status_code;
        if (response->body.content && response->body.length > 0) {
          body.assign(reinterpret_cast<const char*>(response->body.content),
                      response->body.length);
        }
        done = true;
        cv.notify_one();
      });
  lynx_http_service_request(service, request, response);

  {
    std::unique_lock<std::mutex> lock(mutex);
    if (!cv.wait_for(lock, std::chrono::seconds(10), [&]() { return done; })) {
      lynxlib::http::UnregisterCurlHttpService();
      return 2;
    }
  }
  lynxlib::http::UnregisterCurlHttpService();

  if (status_code != 200) {
    return 3;
  }
  if (body.find("\"source\":\"lynxlib-http\"") == std::string::npos) {
    return 4;
  }

  done = false;
  status_code = 0;
  body.clear();

  lynxlib::http::CurlGenericResourceFetcherOptions fetcher_options;
  fetcher_options.cache.policy = lynxlib::http::ResourceCachePolicy::kMemory;
  auto* fetcher =
      lynxlib::http::CreateCurlGenericResourceFetcher(fetcher_options);
  if (!fetcher) {
    return 5;
  }

  auto* resource_request = lynx_resource_request_create(
      resource_server.url().c_str(), 0);
  ResourceCallbackState resource_state{&mutex, &cv, &done, &status_code,
                                       &body};
  auto* resource_response = lynx_resource_response_create(
      [](lynx_resource_response_t* response, void* user_data) {
        auto* state = static_cast<ResourceCallbackState*>(user_data);
        std::lock_guard<std::mutex> lock(*state->mutex);
        *state->status_code = lynx_resource_response_get_code(response);
        const uint8_t* data = lynx_resource_response_get_data(response);
        const size_t length = lynx_resource_response_get_data_length(response);
        if (data && length > 0) {
          state->body->assign(reinterpret_cast<const char*>(data), length);
        }
        *state->done = true;
        state->cv->notify_one();
      },
      &resource_state);
  lynx_generic_resource_fetcher_fetch_resource(fetcher, resource_request,
                                               resource_response);

  {
    std::unique_lock<std::mutex> lock(mutex);
    if (!cv.wait_for(lock, std::chrono::seconds(10), [&]() { return done; })) {
      lynxlib::http::ReleaseCurlGenericResourceFetcher(fetcher);
      return 6;
    }
  }
  lynxlib::http::ReleaseCurlGenericResourceFetcher(fetcher);

  if (status_code != 0) {
    return 7;
  }
  if (body.find("\"source\":\"lynxlib-http\"") == std::string::npos) {
    return 8;
  }
  return 0;
}
