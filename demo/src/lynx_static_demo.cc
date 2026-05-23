#include <windows.h>
#include <shellapi.h>

#include <cstdint>
#include <cstdlib>
#include <cstring>
#include <filesystem>
#include <fstream>
#include <string>
#include <vector>

#include "capi/lynx_load_meta_capi.h"
#include "capi/lynx_template_data_capi.h"
#include "capi/lynx_view_builder_capi.h"
#include "capi/lynx_view_capi.h"

namespace {

constexpr wchar_t kWindowClassName[] = L"LynxStaticDemoWindow";
constexpr wchar_t kWindowTitle[] = L"Lynx static library demo";
constexpr int kInitialWidth = 960;
constexpr int kInitialHeight = 640;

struct ClientSize {
  int physical_width = 0;
  int physical_height = 0;
  float logical_width = 0.0f;
  float logical_height = 0.0f;
  float pixel_ratio = 1.0f;
};

std::filesystem::path ExeDirectory() {
  wchar_t buffer[MAX_PATH] = {};
  const DWORD length = GetModuleFileNameW(nullptr, buffer, MAX_PATH);
  if (length == 0 || length == MAX_PATH) {
    return {};
  }
  return std::filesystem::path(buffer).parent_path();
}

std::filesystem::path DefaultBundlePath() {
  return ExeDirectory() / L"resources" / L"demo" / L"main.lynx.bundle";
}

std::vector<uint8_t> ReadBinaryFile(const std::filesystem::path& path) {
  std::ifstream stream(path, std::ios::binary | std::ios::ate);
  if (!stream) {
    return {};
  }
  const std::streamsize size = stream.tellg();
  if (size <= 0) {
    return {};
  }
  stream.seekg(0, std::ios::beg);
  std::vector<uint8_t> bytes(static_cast<size_t>(size));
  stream.read(reinterpret_cast<char*>(bytes.data()), size);
  return bytes;
}

std::string ToUtf8(const std::filesystem::path& path) {
  return path.u8string();
}

void FreeTemplateBytes(uint8_t* data, size_t, void*) {
  std::free(data);
}

float DpiScaleForWindow(HWND hwnd) {
  HMODULE user32 = GetModuleHandleW(L"user32.dll");
  if (user32) {
    using GetDpiForWindowFn = UINT(WINAPI*)(HWND);
    auto get_dpi_for_window = reinterpret_cast<GetDpiForWindowFn>(
        GetProcAddress(user32, "GetDpiForWindow"));
    if (get_dpi_for_window) {
      return static_cast<float>(get_dpi_for_window(hwnd)) / 96.0f;
    }
  }
  HDC dc = GetDC(hwnd);
  const int dpi = dc ? GetDeviceCaps(dc, LOGPIXELSX) : 96;
  if (dc) {
    ReleaseDC(hwnd, dc);
  }
  return static_cast<float>(dpi) / 96.0f;
}

float DpiScaleForInitialWindow() {
  HMODULE user32 = GetModuleHandleW(L"user32.dll");
  if (user32) {
    using GetDpiForSystemFn = UINT(WINAPI*)();
    auto get_dpi_for_system = reinterpret_cast<GetDpiForSystemFn>(
        GetProcAddress(user32, "GetDpiForSystem"));
    if (get_dpi_for_system) {
      return static_cast<float>(get_dpi_for_system()) / 96.0f;
    }
  }
  HDC dc = GetDC(nullptr);
  const int dpi = dc ? GetDeviceCaps(dc, LOGPIXELSX) : 96;
  if (dc) {
    ReleaseDC(nullptr, dc);
  }
  return static_cast<float>(dpi) / 96.0f;
}

int ScaleForDpi(int value, float pixel_ratio) {
  return static_cast<int>(static_cast<float>(value) * pixel_ratio + 0.5f);
}

ClientSize GetLynxClientSize(HWND hwnd) {
  RECT rect = {};
  GetClientRect(hwnd, &rect);
  ClientSize size;
  size.physical_width = rect.right - rect.left;
  size.physical_height = rect.bottom - rect.top;
  size.pixel_ratio = DpiScaleForWindow(hwnd);
  size.logical_width = static_cast<float>(size.physical_width) / size.pixel_ratio;
  size.logical_height =
      static_cast<float>(size.physical_height) / size.pixel_ratio;
  return size;
}

void EnablePerMonitorDpiAwareness() {
  HMODULE user32 = GetModuleHandleW(L"user32.dll");
  if (user32) {
    using SetProcessDpiAwarenessContextFn = BOOL(WINAPI*)(DPI_AWARENESS_CONTEXT);
    auto set_process_dpi_awareness_context =
        reinterpret_cast<SetProcessDpiAwarenessContextFn>(
            GetProcAddress(user32, "SetProcessDpiAwarenessContext"));
    if (set_process_dpi_awareness_context &&
        set_process_dpi_awareness_context(
            DPI_AWARENESS_CONTEXT_PER_MONITOR_AWARE_V2)) {
      return;
    }
  }
  SetProcessDPIAware();
}

class DemoApp {
 public:
  explicit DemoApp(std::filesystem::path bundle_path)
      : bundle_path_(std::move(bundle_path)) {}

  bool Create(HINSTANCE instance, int show_command) {
    WNDCLASSW window_class = {};
    window_class.hInstance = instance;
    window_class.lpszClassName = kWindowClassName;
    window_class.lpfnWndProc = &DemoApp::WndProc;
    window_class.hCursor = LoadCursor(nullptr, IDC_ARROW);
    window_class.hbrBackground = reinterpret_cast<HBRUSH>(COLOR_WINDOW + 1);
    if (!RegisterClassW(&window_class) && GetLastError() != ERROR_CLASS_ALREADY_EXISTS) {
      return false;
    }

    const float pixel_ratio = DpiScaleForInitialWindow();
    RECT rect = {0, 0, ScaleForDpi(kInitialWidth, pixel_ratio),
                 ScaleForDpi(kInitialHeight, pixel_ratio)};
    AdjustWindowRect(&rect, WS_OVERLAPPEDWINDOW, FALSE);
    hwnd_ = CreateWindowExW(0, kWindowClassName, kWindowTitle,
                            WS_OVERLAPPEDWINDOW, CW_USEDEFAULT, CW_USEDEFAULT,
                            rect.right - rect.left, rect.bottom - rect.top,
                            nullptr, nullptr, instance, this);
    if (!hwnd_) {
      return false;
    }
    ShowWindow(hwnd_, show_command);
    UpdateWindow(hwnd_);
    return true;
  }

  int Run() {
    MSG message = {};
    while (GetMessageW(&message, nullptr, 0, 0) > 0) {
      TranslateMessage(&message);
      DispatchMessageW(&message);
    }
    return static_cast<int>(message.wParam);
  }

 private:
  static LRESULT CALLBACK WndProc(HWND hwnd, UINT message, WPARAM wparam,
                                  LPARAM lparam) {
    DemoApp* app = nullptr;
    if (message == WM_NCCREATE) {
      auto* create = reinterpret_cast<CREATESTRUCTW*>(lparam);
      app = static_cast<DemoApp*>(create->lpCreateParams);
      SetWindowLongPtrW(hwnd, GWLP_USERDATA, reinterpret_cast<LONG_PTR>(app));
      app->hwnd_ = hwnd;
    } else {
      app = reinterpret_cast<DemoApp*>(GetWindowLongPtrW(hwnd, GWLP_USERDATA));
    }

    if (!app) {
      return DefWindowProcW(hwnd, message, wparam, lparam);
    }
    return app->HandleMessage(message, wparam, lparam);
  }

  LRESULT HandleMessage(UINT message, WPARAM wparam, LPARAM lparam) {
    switch (message) {
      case WM_CREATE:
        CreateLynxView();
        return 0;
      case WM_DPICHANGED: {
        auto* suggested_rect = reinterpret_cast<RECT*>(lparam);
        SetWindowPos(hwnd_, nullptr, suggested_rect->left, suggested_rect->top,
                     suggested_rect->right - suggested_rect->left,
                     suggested_rect->bottom - suggested_rect->top,
                     SWP_NOZORDER | SWP_NOACTIVATE);
        return 0;
      }
      case WM_SIZE:
        ResizeLynxView();
        return 0;
      case WM_DESTROY:
        DestroyLynxView();
        PostQuitMessage(0);
        return 0;
      default:
        return DefWindowProcW(hwnd_, message, wparam, lparam);
    }
  }

  void CreateLynxView() {
    const ClientSize size = GetLynxClientSize(hwnd_);

    lynx_view_builder_t* builder = lynx_view_builder_create();
    lynx_view_builder_set_screen_size(builder, size.logical_width,
                                      size.logical_height, size.pixel_ratio);
    lynx_view_builder_set_frame(builder, 0.0f, 0.0f, size.logical_width,
                                size.logical_height);
    lynx_view_builder_set_parent(builder, hwnd_);

    const std::filesystem::path icu_path = ExeDirectory() / L"icudtl.dat";
    if (std::filesystem::exists(icu_path)) {
      const std::string icu_utf8 = ToUtf8(icu_path);
      lynx_view_builder_set_icu_data_path(builder, icu_utf8.c_str());
    }

    lynx_view_ = lynx_view_create(builder, this);
    lynx_view_builder_release(builder);
    if (!lynx_view_) {
      SetWindowTextW(hwnd_, L"Lynx static demo - failed to create LynxView");
      return;
    }

    ResizeLynxView();
    LoadBundle();
  }

  void LoadBundle() {
    std::vector<uint8_t> bytes = ReadBinaryFile(bundle_path_);
    if (bytes.empty()) {
      SetWindowTextW(hwnd_, L"Lynx static demo - bundle missing");
      return;
    }

    uint8_t* owned_bytes =
        static_cast<uint8_t*>(std::malloc(bytes.size()));
    if (!owned_bytes) {
      SetWindowTextW(hwnd_, L"Lynx static demo - out of memory");
      return;
    }
    std::memcpy(owned_bytes, bytes.data(), bytes.size());

    lynx_load_meta_t* load_meta = lynx_load_meta_create();
    lynx_load_meta_set_url(load_meta, "assets://lynxlib-demo");
    lynx_load_meta_set_binary_data(load_meta, owned_bytes, bytes.size(),
                                   &FreeTemplateBytes, nullptr);

    lynx_template_data_t* global_props =
        lynx_template_data_create_from_json("{\"platform\":\"windows\",\"linked\":\"lynx_static.lib\"}");
    lynx_load_meta_set_global_props(load_meta, global_props);

    lynx_view_load_template(lynx_view_, load_meta);
    lynx_load_meta_release(load_meta);
    SetWindowTextW(hwnd_, kWindowTitle);
  }

  void ResizeLynxView() {
    if (!lynx_view_) {
      return;
    }
    const ClientSize size = GetLynxClientSize(hwnd_);
    lynx_view_update_screen_metrics(lynx_view_, size.logical_width,
                                    size.logical_height, size.pixel_ratio);
    lynx_view_set_frame(lynx_view_, 0.0f, 0.0f, size.logical_width,
                        size.logical_height);
  }

  void DestroyLynxView() {
    if (lynx_view_) {
      lynx_view_release(lynx_view_);
      lynx_view_ = nullptr;
    }
  }

  HWND hwnd_ = nullptr;
  lynx_view_t* lynx_view_ = nullptr;
  std::filesystem::path bundle_path_;
};

std::filesystem::path ParseBundlePathFromCommandLine() {
  int argc = 0;
  LPWSTR* argv = CommandLineToArgvW(GetCommandLineW(), &argc);
  std::filesystem::path bundle_path = DefaultBundlePath();
  if (argv && argc > 1) {
    bundle_path = argv[1];
  }
  if (argv) {
    LocalFree(argv);
  }
  return bundle_path;
}

}  // namespace

int WINAPI wWinMain(HINSTANCE instance, HINSTANCE, PWSTR, int show_command) {
  EnablePerMonitorDpiAwareness();
  DemoApp app(ParseBundlePathFromCommandLine());
  if (!app.Create(instance, show_command)) {
    MessageBoxW(nullptr, L"Failed to create the demo window.",
                L"Lynx static demo", MB_ICONERROR | MB_OK);
    return 1;
  }
  return app.Run();
}
