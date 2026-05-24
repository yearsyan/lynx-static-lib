#ifndef LYNXLIB_HTTP_SERVICE_H_
#define LYNXLIB_HTTP_SERVICE_H_

#include <cstddef>

namespace lynxlib {
namespace http {

struct CurlHttpServiceOptions {
  long connect_timeout_ms = 15000;
  long request_timeout_ms = 0;
  long max_redirects = 5;
  bool follow_redirects = true;
  bool verbose = false;
  std::size_t max_response_bytes = 64 * 1024 * 1024;
};

void RegisterCurlHttpService(const CurlHttpServiceOptions& options = {});
void UnregisterCurlHttpService();

}  // namespace http
}  // namespace lynxlib

extern "C" void lynxlib_http_register_default_service();
extern "C" void lynxlib_http_unregister_service();

#endif  // LYNXLIB_HTTP_SERVICE_H_
