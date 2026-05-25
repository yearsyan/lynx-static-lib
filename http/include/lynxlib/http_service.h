#ifndef LYNXLIB_HTTP_SERVICE_H_
#define LYNXLIB_HTTP_SERVICE_H_

#include <cstddef>

extern "C" {
typedef struct lynx_generic_resource_fetcher_t lynx_generic_resource_fetcher_t;
}

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

enum class ResourceCachePolicy {
  kDisabled,
  kMemory,
};

struct ResourceCacheOptions {
  ResourceCachePolicy policy = ResourceCachePolicy::kDisabled;
  std::size_t max_entries = 128;
  std::size_t max_bytes = 64 * 1024 * 1024;
  long ttl_ms = 5 * 60 * 1000;
};

struct CurlGenericResourceFetcherOptions {
  CurlHttpServiceOptions http;
  ResourceCacheOptions cache;
  bool share_registered_http_service = true;
};

void RegisterCurlHttpService(const CurlHttpServiceOptions& options = {});
void UnregisterCurlHttpService();

lynx_generic_resource_fetcher_t* CreateCurlGenericResourceFetcher(
    const CurlGenericResourceFetcherOptions& options = {});
void ReleaseCurlGenericResourceFetcher(
    lynx_generic_resource_fetcher_t* fetcher);

}  // namespace http
}  // namespace lynxlib

extern "C" void lynxlib_http_register_default_service();
extern "C" void lynxlib_http_unregister_service();
extern "C" lynx_generic_resource_fetcher_t*
lynxlib_http_create_default_generic_resource_fetcher();
extern "C" lynx_generic_resource_fetcher_t*
lynxlib_http_create_memory_cached_generic_resource_fetcher(
    std::size_t max_entries, std::size_t max_bytes, long ttl_ms);
extern "C" void lynxlib_http_release_generic_resource_fetcher(
    lynx_generic_resource_fetcher_t* fetcher);

#endif  // LYNXLIB_HTTP_SERVICE_H_
