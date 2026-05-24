#include <memory>
#include <string>

#include "lynxlib_embedded_core_js_data.h"
#include "platform/embedder/public/capi/lynx_env_capi.h"
#include "platform/embedder/resource/core_js_loader_manager.h"

namespace {

class EmbeddedCoreJsLoader final : public lynx::ICoreJsLoader {
 public:
  EmbeddedCoreJsLoader()
      : source_(reinterpret_cast<const char*>(
                    lynxlib::embedded_core_js::kCoreJsBytes),
                lynxlib::embedded_core_js::kCoreJsSize) {}

  const char* GetCoreJs() override { return source_.c_str(); }
  bool JsCoreUpdated() override { return false; }
  void CheckUpdate() override {}

 private:
  std::string source_;
};

class EmbeddedRuntimeBootstrap {
 public:
  EmbeddedRuntimeBootstrap() {
    lynx::CoreJsLoaderManager::GetInstance()->SetLoader(
        std::make_unique<EmbeddedCoreJsLoader>());

    lynx_env_enable_devtool(lynxlib::embedded_core_js::kDevBuild ? 1 : 0);
    lynx_env_enable_logbox(lynxlib::embedded_core_js::kDevBuild ? 1 : 0);
  }
};

EmbeddedRuntimeBootstrap g_bootstrap;

}  // namespace

extern "C" void lynxlib_force_link_embedded_core_js() {}
