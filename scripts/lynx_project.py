from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import struct
import subprocess
import sys
from pathlib import Path


DEFAULT_LYNXLIB_REF = "lynxlib/0.1.4@neuyan/stable"
DEFAULT_RUNTIME_REF = "lynxlib-runtime/0.1.4@neuyan/stable"
DEFAULT_REMOTE = "neuyan"


def log(message: str) -> None:
    print(message, flush=True)


def run(command: list[str], cwd: Path, env: dict[str, str] | None = None) -> None:
    log(" ".join(str(part) for part in command))
    resolved = shutil.which(command[0], path=(env or os.environ).get("PATH"))
    actual_command = [resolved or command[0], *command[1:]]
    if os.name == "nt" and Path(actual_command[0]).suffix.lower() in {".bat", ".cmd"}:
        actual_command = ["cmd.exe", "/d", "/c", *actual_command]
    completed = subprocess.run(actual_command, cwd=str(cwd), env=env)
    if completed.returncode != 0:
        raise RuntimeError(
            f"Command failed with exit code {completed.returncode}: {' '.join(command)}"
        )


def read_json(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as stream:
        return json.load(stream)


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as stream:
        stream.write(text)


def write_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def sanitize_identifier(value: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9_]+", "_", value.strip())
    cleaned = re.sub(r"_+", "_", cleaned).strip("_")
    if not cleaned:
        cleaned = "lynx_app"
    if cleaned[0].isdigit():
        cleaned = f"lynx_{cleaned}"
    return cleaned


def sanitize_package_name(value: str) -> str:
    cleaned = re.sub(r"[^a-z0-9-]+", "-", value.strip().lower())
    cleaned = re.sub(r"-+", "-", cleaned).strip("-")
    return cleaned or "lynx-app"


def validate_project_name(name: str) -> str:
    name = name.strip()
    if not name:
        raise RuntimeError("Project name cannot be empty.")
    if not re.fullmatch(r"[A-Za-z][A-Za-z0-9_-]*", name):
        raise RuntimeError(
            "Project name must start with a letter and contain only letters, digits, '-' or '_'."
        )
    return name


def prompt_project_name(default: str | None = None) -> str:
    suffix = f" [{default}]" if default else ""
    entered = input(f"Project name{suffix}: ").strip()
    return validate_project_name(entered or (default or ""))


def c_string(value: str) -> str:
    return (
        value.replace("\\", "\\\\")
        .replace('"', '\\"')
        .replace("\n", "\\n")
        .replace("\r", "\\r")
    )


def cmake_bool(value: bool) -> str:
    return "ON" if value else "OFF"


def find_visual_studio_root(env: dict[str, str]) -> Path:
    override = env.get("GYP_MSVS_OVERRIDE_PATH")
    if override:
        candidate = Path(override)
        if (candidate / "VC" / "Auxiliary" / "Build" / "vcvarsall.bat").exists():
            return candidate

    for base in [
        Path("C:/Program Files/Microsoft Visual Studio/2022"),
        Path("C:/Program Files (x86)/Microsoft Visual Studio/2022"),
    ]:
        for edition in ["BuildTools", "Community", "Professional", "Enterprise"]:
            candidate = base / edition
            if (candidate / "VC" / "Auxiliary" / "Build" / "vcvarsall.bat").exists():
                return candidate
    raise RuntimeError("Visual Studio 2022 C++ build tools were not found.")


def load_vcvars_environment(env: dict[str, str]) -> None:
    vs_root = find_visual_studio_root(env)
    env["GYP_MSVS_OVERRIDE_PATH"] = str(vs_root)
    vcvars = vs_root / "VC" / "Auxiliary" / "Build" / "vcvarsall.bat"
    command = f'cmd.exe /d /c call "{vcvars}" x64 ^>nul ^&^& set'
    completed = subprocess.run(
        command,
        env=env,
        shell=True,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    if completed.returncode != 0:
        if completed.stdout:
            sys.stdout.write(completed.stdout)
        if completed.stderr:
            sys.stderr.write(completed.stderr)
        raise RuntimeError(f"Failed to load Visual Studio environment from {vcvars}")
    for line in completed.stdout.splitlines():
        if "=" in line:
            key, value = line.split("=", 1)
            env[key] = value


def ensure_ninja_on_path(env: dict[str, str]) -> None:
    if shutil.which("ninja", path=env.get("PATH")):
        return
    vs_root = env.get("GYP_MSVS_OVERRIDE_PATH")
    if vs_root:
        candidate = (
            Path(vs_root)
            / "Common7"
            / "IDE"
            / "CommonExtensions"
            / "Microsoft"
            / "CMake"
            / "Ninja"
        )
        if (candidate / "ninja.exe").exists():
            env["PATH"] = str(candidate) + os.pathsep + env.get("PATH", "")
            return
    raise RuntimeError("ninja.exe was not found.")


def find_cmake() -> str:
    candidates = [
        shutil.which("cmake"),
        "C:/Program Files/CMake/bin/cmake.exe",
        "C:/Program Files/Microsoft Visual Studio/2022/Community/Common7/IDE/CommonExtensions/Microsoft/CMake/CMake/bin/cmake.exe",
        "C:/Program Files/Microsoft Visual Studio/2022/BuildTools/Common7/IDE/CommonExtensions/Microsoft/CMake/CMake/bin/cmake.exe",
    ]
    for candidate in candidates:
        if candidate and Path(candidate).exists():
            return str(Path(candidate))
    raise RuntimeError("cmake.exe was not found.")


def write_default_icon(path: Path) -> None:
    width = 32
    height = 32
    pixels = bytearray()
    for y in reversed(range(height)):
        for x in range(width):
            edge = x in (0, width - 1) or y in (0, height - 1)
            r = 28 if edge else 32 + x * 4
            g = 99 if edge else 92 + y * 3
            b = 170 if edge else 180
            a = 255
            pixels.extend([b & 0xFF, g & 0xFF, r & 0xFF, a])
    mask = bytes(((width + 31) // 32) * 4 * height)
    dib = struct.pack(
        "<IIIHHIIIIII",
        40,
        width,
        height * 2,
        1,
        32,
        0,
        len(pixels),
        0,
        0,
        0,
        0,
    ) + bytes(pixels) + mask
    header = struct.pack("<HHH", 0, 1, 1)
    entry = struct.pack("<BBBBHHII", width, height, 0, 0, 1, 32, len(dib), 22)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(header + entry + dib)


def scaffold_config(project_name: str) -> dict:
    target = sanitize_identifier(project_name)
    package_name = sanitize_package_name(project_name)
    return {
        "name": project_name,
        "target": target,
        "display_name": project_name.replace("_", " ").replace("-", " ").title(),
        "version": "0.1.0",
        "conan": {
            "remote": DEFAULT_REMOTE,
            "lynxlib": DEFAULT_LYNXLIB_REF,
            "runtime": DEFAULT_RUNTIME_REF,
            "profile": "profiles/windows-msvc-static",
        },
        "bundle": {
            "source_dir": "bundle",
            "main": "bundle/dist/main.lynx.bundle",
            "embed_main_bundle": True,
            "install_command": ["pnpm", "install"],
            "build_command": ["pnpm", "exec", "rspeedy", "build"],
        },
        "runtime": {
            "copy_icu": True,
        },
        "compile_commands": {
            "copy_to_root": True,
            "path": "compile_commands.json",
        },
        "windows": {
            "icon": "assets/app.ico",
        },
        "package": {
            "name": package_name,
        },
    }


CMAKE_TEMPLATE = r"""
cmake_minimum_required(VERSION 3.23)

project(@TARGET@ LANGUAGES CXX)

if(NOT WIN32)
  message(FATAL_ERROR "Generated Lynx projects currently support Windows only.")
endif()

enable_language(RC)

set(LYNX_PROJECT_EXECUTABLE "@TARGET@")
set(LYNX_PROJECT_GENERATED_DIR "${CMAKE_CURRENT_BINARY_DIR}/generated")
set(LYNX_PROJECT_BUNDLE "${CMAKE_CURRENT_SOURCE_DIR}/bundle/dist/main.lynx.bundle")
set(LYNX_PROJECT_EMBED_BUNDLE ON)
set(LYNX_PROJECT_COPY_ICU ON)
set(LYNX_PROJECT_ICON_RC "")

include("${CMAKE_CURRENT_BINARY_DIR}/generated/project_options.cmake" OPTIONAL)

find_package(lynxlib CONFIG REQUIRED)
find_package(lynxlib_runtime CONFIG REQUIRED)

set(LYNX_PROJECT_SOURCES
  src/main.cpp)

if(LYNX_PROJECT_ICON_RC AND EXISTS "${LYNX_PROJECT_ICON_RC}")
  list(APPEND LYNX_PROJECT_SOURCES "${LYNX_PROJECT_ICON_RC}")
endif()

add_executable(${LYNX_PROJECT_EXECUTABLE} WIN32
  ${LYNX_PROJECT_SOURCES})

target_compile_features(${LYNX_PROJECT_EXECUTABLE} PRIVATE cxx_std_17)
target_compile_definitions(${LYNX_PROJECT_EXECUTABLE} PRIVATE
  WIN32_LEAN_AND_MEAN
  NOMINMAX)
target_include_directories(${LYNX_PROJECT_EXECUTABLE} PRIVATE
  "${LYNX_PROJECT_GENERATED_DIR}")
set_property(TARGET ${LYNX_PROJECT_EXECUTABLE} PROPERTY
  MSVC_RUNTIME_LIBRARY "MultiThreaded$<$<CONFIG:Debug>:Debug>")
target_link_libraries(${LYNX_PROJECT_EXECUTABLE} PRIVATE lynxlib::lynxlib)

if(MSVC)
  target_compile_options(${LYNX_PROJECT_EXECUTABLE} PRIVATE /EHsc)
  target_link_options(${LYNX_PROJECT_EXECUTABLE} PRIVATE "/INCLUDE:?SetupWeakNodeApiEnv@napi@primjs@@YAXXZ")
endif()

if(LYNX_PROJECT_COPY_ICU)
  if(COMMAND lynxlib_copy_runtime_assets)
    lynxlib_copy_runtime_assets(${LYNX_PROJECT_EXECUTABLE})
  else()
    message(FATAL_ERROR "lynxlib runtime asset helper was not loaded from the Conan package.")
  endif()
endif()

if(NOT LYNX_PROJECT_EMBED_BUNDLE)
  if(NOT EXISTS "${LYNX_PROJECT_BUNDLE}")
    message(FATAL_ERROR "Bundle not found: ${LYNX_PROJECT_BUNDLE}")
  endif()
  add_custom_target(${LYNX_PROJECT_EXECUTABLE}_resources ALL
    COMMAND "${CMAKE_COMMAND}" -E make_directory
            "$<TARGET_FILE_DIR:${LYNX_PROJECT_EXECUTABLE}>/resources"
    COMMAND "${CMAKE_COMMAND}" -E copy_if_different
            "${LYNX_PROJECT_BUNDLE}"
            "$<TARGET_FILE_DIR:${LYNX_PROJECT_EXECUTABLE}>/resources/main.lynx.bundle"
    DEPENDS "${LYNX_PROJECT_BUNDLE}"
    COMMENT "Copying Lynx bundle")
  add_dependencies(${LYNX_PROJECT_EXECUTABLE} ${LYNX_PROJECT_EXECUTABLE}_resources)
endif()
"""


MAIN_CPP_TEMPLATE = r"""
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
#include "generated_bundle.h"
#include "generated_config.h"

namespace {

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
  return ExeDirectory() / L"resources" / L"main.lynx.bundle";
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

class LynxApp {
 public:
  explicit LynxApp(std::filesystem::path bundle_path)
      : bundle_path_(std::move(bundle_path)) {}

  bool Create(HINSTANCE instance, int show_command) {
    WNDCLASSW window_class = {};
    window_class.hInstance = instance;
    window_class.lpszClassName = generated::kWindowClassName;
    window_class.lpfnWndProc = &LynxApp::WndProc;
    window_class.hCursor = LoadCursor(nullptr, IDC_ARROW);
    window_class.hbrBackground = reinterpret_cast<HBRUSH>(COLOR_WINDOW + 1);
    if (!RegisterClassW(&window_class) && GetLastError() != ERROR_CLASS_ALREADY_EXISTS) {
      return false;
    }

    const float pixel_ratio = DpiScaleForInitialWindow();
    RECT rect = {0, 0, ScaleForDpi(kInitialWidth, pixel_ratio),
                 ScaleForDpi(kInitialHeight, pixel_ratio)};
    AdjustWindowRect(&rect, WS_OVERLAPPEDWINDOW, FALSE);
    hwnd_ = CreateWindowExW(0, generated::kWindowClassName,
                            generated::kWindowTitle, WS_OVERLAPPEDWINDOW,
                            CW_USEDEFAULT, CW_USEDEFAULT,
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
    LynxApp* app = nullptr;
    if (message == WM_NCCREATE) {
      auto* create = reinterpret_cast<CREATESTRUCTW*>(lparam);
      app = static_cast<LynxApp*>(create->lpCreateParams);
      SetWindowLongPtrW(hwnd, GWLP_USERDATA, reinterpret_cast<LONG_PTR>(app));
      app->hwnd_ = hwnd;
    } else {
      app = reinterpret_cast<LynxApp*>(GetWindowLongPtrW(hwnd, GWLP_USERDATA));
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
      SetWindowTextW(hwnd_, L"Failed to create LynxView");
      return;
    }

    ResizeLynxView();
    LoadBundle();
  }

  std::vector<uint8_t> LoadBundleBytes() {
    if (generated::kEmbeddedBundle) {
      return std::vector<uint8_t>(
          generated::kBundle,
          generated::kBundle + generated::kBundleSize);
    }
    return ReadBinaryFile(bundle_path_);
  }

  void LoadBundle() {
    std::vector<uint8_t> bytes = LoadBundleBytes();
    if (bytes.empty()) {
      SetWindowTextW(hwnd_, L"Lynx bundle missing");
      return;
    }

    uint8_t* owned_bytes = static_cast<uint8_t*>(std::malloc(bytes.size()));
    if (!owned_bytes) {
      SetWindowTextW(hwnd_, L"Out of memory");
      return;
    }
    std::memcpy(owned_bytes, bytes.data(), bytes.size());

    lynx_load_meta_t* load_meta = lynx_load_meta_create();
    lynx_load_meta_set_url(load_meta, generated::kTemplateUrl);
    lynx_load_meta_set_binary_data(load_meta, owned_bytes, bytes.size(),
                                   &FreeTemplateBytes, nullptr);

    lynx_template_data_t* global_props =
        lynx_template_data_create_from_json(generated::kGlobalPropsJson);
    lynx_load_meta_set_global_props(load_meta, global_props);

    lynx_view_load_template(lynx_view_, load_meta);
    lynx_load_meta_release(load_meta);
    SetWindowTextW(hwnd_, generated::kWindowTitle);
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
  LynxApp app(ParseBundlePathFromCommandLine());
  if (!app.Create(instance, show_command)) {
    MessageBoxW(nullptr, L"Failed to create the Lynx window.",
                generated::kWindowTitle, MB_ICONERROR | MB_OK);
    return 1;
  }
  return app.Run();
}
"""


INDEX_TSX_TEMPLATE = r"""
import { root } from "@lynx-js/react";

import "./styles.scss";

function App() {
  return (
    <view className="page">
      <view className="hero">
        <text className="eyebrow">lynxlib conan project</text>
        <text className="title">@DISPLAY_NAME@</text>
        <text className="subtitle">Native Win32 shell, Conan powered static SDK.</text>
      </view>
      <view className="grid">
        <view className="tile blue">
          <text className="tileLabel">Bundle</text>
          <text className="tileValue">Configurable</text>
        </view>
        <view className="tile green">
          <text className="tileLabel">SDK</text>
          <text className="tileValue">Static link</text>
        </view>
        <view className="tile gold">
          <text className="tileLabel">Build</text>
          <text className="tileValue">compile_commands</text>
        </view>
      </view>
      <view className="panel">
        <text className="panelTitle">Edit bundle/src/index.tsx and rebuild.</text>
        <text className="panelText">Toggle bundle.embed_main_bundle in lynx_project.json to embed this bundle into the exe.</text>
      </view>
    </view>
  );
}

root.render(<App />);

if (import.meta.webpackHot) {
  import.meta.webpackHot.accept();
}
"""


STYLES_TEMPLATE = r"""
.page {
  width: 100%;
  height: 100%;
  display: flex;
  flex-direction: column;
  background-color: #f7f8fb;
  row-gap: 20px;
}

.hero {
  display: flex;
  flex-direction: column;
  background-color: #ffffff;
  border-radius: 6px;
  margin-left: 28px;
  margin-right: 28px;
  margin-top: 28px;
  padding: 28px;
  row-gap: 12px;
}

.eyebrow {
  color: #2563eb;
  font-size: 14px;
  font-weight: 700;
}

.title {
  color: #111827;
  font-size: 34px;
  font-weight: 800;
}

.subtitle {
  color: #374151;
  font-size: 18px;
}

.grid {
  display: flex;
  flex-direction: row;
  column-gap: 16px;
  margin-left: 28px;
  margin-right: 28px;
}

.tile {
  flex: 1;
  display: flex;
  flex-direction: column;
  border-radius: 6px;
  padding: 20px;
  row-gap: 8px;
}

.blue {
  background-color: #dbeafe;
}

.green {
  background-color: #dcfce7;
}

.gold {
  background-color: #fef3c7;
}

.tileLabel {
  color: #4b5563;
  font-size: 14px;
  font-weight: 700;
}

.tileValue {
  color: #111827;
  font-size: 20px;
  font-weight: 800;
}

.panel {
  display: flex;
  flex-direction: column;
  background-color: #111827;
  border-radius: 6px;
  margin-left: 28px;
  margin-right: 28px;
  padding: 20px;
  row-gap: 8px;
}

.panelTitle {
  color: #ffffff;
  font-size: 18px;
  font-weight: 800;
}

.panelText {
  color: #d1d5db;
  font-size: 15px;
}
"""


LYNX_CONFIG_TEMPLATE = r"""
import { pluginReactLynx } from "@lynx-js/react-rsbuild-plugin";
import { defineConfig } from "@lynx-js/rspeedy";
import { pluginSass } from "@rsbuild/plugin-sass";

export default defineConfig({
  source: {
    entry: {
      main: "./src/index.tsx",
    },
  },
  output: {
    distPath: {
      root: "./dist",
    },
  },
  plugins: [
    pluginReactLynx({
      defaultDisplayLinear: false,
    }),
    pluginSass(),
  ],
  environments: {
    lynx: {},
  },
});
"""


CONANFILE_TEMPLATE = r"""
from __future__ import annotations

from conan import ConanFile
from conan.tools.cmake import CMakeDeps, CMakeToolchain, cmake_layout


class GeneratedLynxProjectConan(ConanFile):
    name = "@PACKAGE_NAME@"
    version = "@VERSION@"
    settings = "os", "arch", "compiler", "build_type"

    def requirements(self) -> None:
        self.requires("@LYNXLIB_REF@")
        self.requires("@RUNTIME_REF@")

    def layout(self) -> None:
        cmake_layout(self)

    def generate(self) -> None:
        deps = CMakeDeps(self)
        deps.generate()

        toolchain = CMakeToolchain(self)
        toolchain.cache_variables["CMAKE_EXPORT_COMPILE_COMMANDS"] = "ON"
        toolchain.cache_variables["CMAKE_MSVC_RUNTIME_LIBRARY"] = "MultiThreaded$<$<CONFIG:Debug>:Debug>"
        toolchain.generate()
"""


PROFILE_TEMPLATE = r"""
[settings]
os=Windows
arch=x86_64
compiler=msvc
compiler.version=194
compiler.runtime=static
compiler.cppstd=17
build_type=Release

[conf]
tools.cmake.cmaketoolchain:generator=Ninja
"""


README_TEMPLATE = r"""
# @DISPLAY_NAME@

This project was generated by `lynx_project.py`.

Useful commands:

```powershell
python path\to\lynx_project.py build .
python path\to\lynx_project.py build . --export
python path\to\lynx_project.py export .
```

Publish `dist/<build-type>/`, not `build/<build-type>/`. The build directory is
an internal CMake/Conan workspace and contains development artifacts that are
not part of the redistributable app.

Project behavior is controlled by `lynx_project.json`.
Set `bundle.embed_main_bundle` to `true` to compile `bundle/dist/main.lynx.bundle`
into `build/<build-type>/generated/generated_bundle.h`; set it to `false` to
copy the bundle next to the executable under `resources/main.lynx.bundle`.

`compile_commands.copy_to_root` copies the CMake-generated compile database to
`compile_commands.json` in the project root for clangd and editor integrations.
"""


GITIGNORE_TEMPLATE = r"""
/build/
/bundle/node_modules/
/bundle/dist/
/bundle/package-lock.json
/bundle/pnpm-lock.yaml
/compile_commands.json
/dist/
CMakeUserPresets.json
"""


def template_replace(text: str, values: dict[str, str]) -> str:
    for key, value in values.items():
        text = text.replace(f"@{key}@", value)
    return text.strip() + "\n"


def ensure_generated_dir(build_dir: Path) -> Path:
    generated = build_dir / "generated"
    generated.mkdir(parents=True, exist_ok=True)
    return generated


def create_project(args: argparse.Namespace) -> None:
    default_name = Path(args.path).name if args.path else None
    project_name = validate_project_name(args.name) if args.name else prompt_project_name(default_name)
    if args.root:
        project_dir = Path(args.root) / project_name
    elif args.path:
        project_dir = Path(args.path)
    else:
        project_dir = Path.cwd() / project_name
    project_dir = project_dir.resolve()

    if project_dir.exists() and any(project_dir.iterdir()):
        if not args.force:
            raise RuntimeError(f"Project directory is not empty: {project_dir}")
        marker = project_dir / "lynx_project.json"
        if not marker.exists():
            raise RuntimeError(f"Refusing to overwrite a directory without lynx_project.json: {project_dir}")
        shutil.rmtree(project_dir)

    config = scaffold_config(project_name)
    target = config["target"]
    package_name = config["package"]["name"]
    values = {
        "PROJECT_NAME": project_name,
        "TARGET": target,
        "DISPLAY_NAME": config["display_name"],
        "PACKAGE_NAME": package_name,
        "VERSION": config["version"],
        "LYNXLIB_REF": config["conan"]["lynxlib"],
        "RUNTIME_REF": config["conan"]["runtime"],
    }

    write_json(project_dir / "lynx_project.json", config)
    write_text(project_dir / "CMakeLists.txt", template_replace(CMAKE_TEMPLATE, values))
    write_text(project_dir / "src" / "main.cpp", template_replace(MAIN_CPP_TEMPLATE, values))
    write_text(project_dir / "conanfile.py", template_replace(CONANFILE_TEMPLATE, values))
    write_text(project_dir / "profiles" / "windows-msvc-static", PROFILE_TEMPLATE.strip() + "\n")
    write_text(project_dir / "README.md", template_replace(README_TEMPLATE, values))
    write_text(project_dir / ".gitignore", GITIGNORE_TEMPLATE.strip() + "\n")

    package_json = {
        "name": f"{package_name}-bundle",
        "private": True,
        "type": "module",
        "scripts": {"build": "rspeedy build"},
        "dependencies": {"@lynx-js/react": "0.107.0"},
        "devDependencies": {
            "@lynx-js/react-rsbuild-plugin": "0.9.8",
            "@lynx-js/rspeedy": "0.9.3",
            "@rsbuild/plugin-sass": "1.3.1",
            "typescript": "5.8.3",
        },
    }
    write_json(project_dir / "bundle" / "package.json", package_json)
    write_text(project_dir / "bundle" / "lynx.config.mjs", LYNX_CONFIG_TEMPLATE.strip() + "\n")
    write_text(
        project_dir / "bundle" / "src" / "index.tsx",
        template_replace(INDEX_TSX_TEMPLATE, values),
    )
    write_text(project_dir / "bundle" / "src" / "styles.scss", STYLES_TEMPLATE.strip() + "\n")
    write_default_icon(project_dir / "assets" / "app.ico")
    log(f"Created Lynx project: {project_dir}")


def project_config_path(project_dir: Path) -> Path:
    config = project_dir / "lynx_project.json"
    if not config.exists():
        raise RuntimeError(f"lynx_project.json was not found in {project_dir}")
    return config


def resolve_project_path(project_dir: Path, value: str | None) -> Path | None:
    if not value:
        return None
    path = Path(value)
    if not path.is_absolute():
        path = project_dir / path
    return path.resolve()


def build_bundle(project_dir: Path, config: dict, env: dict[str, str]) -> None:
    bundle = config.get("bundle", {})
    source_dir = resolve_project_path(project_dir, bundle.get("source_dir", "bundle"))
    if source_dir is None:
        raise RuntimeError("bundle.source_dir is not configured.")

    output = resolve_project_path(project_dir, bundle.get("main", "bundle/dist/main.lynx.bundle"))
    if output is None:
        raise RuntimeError("bundle.main is not configured.")

    rspeedy = source_dir / "node_modules" / "@lynx-js" / "rspeedy" / "bin" / "rspeedy.js"
    if not rspeedy.exists():
        install_command = bundle.get("install_command") or ["pnpm", "install"]
        run([str(part) for part in install_command], cwd=source_dir, env=env)

    build_command = bundle.get("build_command") or ["pnpm", "exec", "rspeedy", "build"]
    run([str(part) for part in build_command], cwd=source_dir, env=env)
    if not output.exists():
        raise RuntimeError(f"Bundle build did not produce {output}")


def migrate_cmake_generated_dir(project_dir: Path) -> None:
    cmake_lists = project_dir / "CMakeLists.txt"
    if not cmake_lists.exists():
        return

    text = cmake_lists.read_text(encoding="utf-8")
    updated = text.replace(
        'set(LYNX_PROJECT_GENERATED_DIR "${CMAKE_CURRENT_SOURCE_DIR}/generated")',
        'set(LYNX_PROJECT_GENERATED_DIR "${CMAKE_CURRENT_BINARY_DIR}/generated")',
    ).replace(
        'include("${CMAKE_CURRENT_SOURCE_DIR}/generated/project_options.cmake" OPTIONAL)',
        'include("${CMAKE_CURRENT_BINARY_DIR}/generated/project_options.cmake" OPTIONAL)',
    )
    if updated != text:
        write_text(cmake_lists, updated)
        log(f"Updated generated output path in: {cmake_lists}")


def generate_bundle_header(project_dir: Path, build_dir: Path, config: dict) -> None:
    bundle = config.get("bundle", {})
    output = resolve_project_path(project_dir, bundle.get("main", "bundle/dist/main.lynx.bundle"))
    embed = bool(bundle.get("embed_main_bundle", True))
    generated = ensure_generated_dir(build_dir)

    if embed:
        if output is None or not output.exists():
            raise RuntimeError(f"Cannot embed missing bundle: {output}")
        data = output.read_bytes()
        chunks = []
        for offset in range(0, len(data), 12):
            line = ", ".join(f"0x{byte:02x}" for byte in data[offset : offset + 12])
            chunks.append(f"  {line},")
        array_body = "\n".join(chunks)
        header = f"""#pragma once

#include <cstddef>
#include <cstdint>

namespace generated {{
inline constexpr bool kEmbeddedBundle = true;
inline const std::uint8_t kBundle[] = {{
{array_body}
}};
inline constexpr std::size_t kBundleSize = sizeof(kBundle);
}}  // namespace generated
"""
    else:
        header = """#pragma once

#include <cstddef>
#include <cstdint>

namespace generated {
inline constexpr bool kEmbeddedBundle = false;
inline const std::uint8_t kBundle[1] = {0};
inline constexpr std::size_t kBundleSize = 0;
}  // namespace generated
"""
    write_text(generated / "generated_bundle.h", header)


def generate_config_files(project_dir: Path, build_dir: Path, config: dict) -> None:
    generated = ensure_generated_dir(build_dir)
    target = sanitize_identifier(config.get("target") or config.get("name") or "lynx_app")
    display_name = str(config.get("display_name") or config.get("name") or target)
    template_url = f"assets://{target}/main"
    props = json.dumps(
        {
            "platform": "windows",
            "project": config.get("name", target),
            "embeddedBundle": bool(config.get("bundle", {}).get("embed_main_bundle", True)),
        },
        separators=(",", ":"),
    )
    config_header = f"""#pragma once

namespace generated {{
inline constexpr wchar_t kWindowClassName[] = L"{c_string(target)}Window";
inline constexpr wchar_t kWindowTitle[] = L"{c_string(display_name)}";
inline constexpr char kTemplateUrl[] = "{c_string(template_url)}";
inline constexpr char kGlobalPropsJson[] = "{c_string(props)}";
}}  // namespace generated
"""
    write_text(generated / "generated_config.h", config_header)

    bundle = config.get("bundle", {})
    bundle_path = resolve_project_path(project_dir, bundle.get("main", "bundle/dist/main.lynx.bundle"))
    windows = config.get("windows", {})
    icon = resolve_project_path(project_dir, windows.get("icon"))
    rc_path = generated / "windows_resources.rc"
    if icon and icon.exists():
        icon_for_rc = str(icon).replace("\\", "/")
        write_text(
            rc_path,
            f"""#include <windows.h>

IDI_APP_ICON ICON "{icon_for_rc}"
""",
        )
        icon_rc_value = str(rc_path).replace("\\", "/")
    else:
        if rc_path.exists():
            rc_path.unlink()
        icon_rc_value = ""

    project_options = f"""set(LYNX_PROJECT_EXECUTABLE "{c_string(target)}")
set(LYNX_PROJECT_GENERATED_DIR "{str(generated).replace("\\", "/")}")
set(LYNX_PROJECT_BUNDLE "{str(bundle_path).replace("\\", "/") if bundle_path else ""}")
set(LYNX_PROJECT_EMBED_BUNDLE {cmake_bool(bool(bundle.get("embed_main_bundle", True)))})
set(LYNX_PROJECT_COPY_ICU {cmake_bool(bool(config.get("runtime", {}).get("copy_icu", True)))})
set(LYNX_PROJECT_ICON_RC "{icon_rc_value}")
"""
    write_text(generated / "project_options.cmake", project_options)


def generate_conanfile(project_dir: Path, config: dict) -> None:
    conan = config.get("conan", {})
    package = config.get("package", {})
    values = {
        "PACKAGE_NAME": sanitize_package_name(package.get("name") or config.get("name") or "lynx-app"),
        "VERSION": str(config.get("version") or "0.1.0"),
        "LYNXLIB_REF": str(conan.get("lynxlib") or DEFAULT_LYNXLIB_REF),
        "RUNTIME_REF": str(conan.get("runtime") or DEFAULT_RUNTIME_REF),
    }
    write_text(project_dir / "conanfile.py", template_replace(CONANFILE_TEMPLATE, values))


def sync_compile_commands(project_dir: Path, build_dir: Path, config: dict) -> None:
    settings = config.get("compile_commands", {})
    if isinstance(settings, bool):
        copy_to_root = settings
        output_path = "compile_commands.json"
    else:
        copy_to_root = bool(settings.get("copy_to_root", True))
        output_path = str(settings.get("path") or "compile_commands.json")

    if not copy_to_root:
        return

    source = build_dir / "compile_commands.json"
    if not source.exists():
        return

    destination = resolve_project_path(project_dir, output_path)
    if destination is None:
        return
    if source.resolve() == destination.resolve():
        log(f"compile_commands.json: {source}")
        return

    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, destination)
    log(f"compile_commands.json: {source}")
    log(f"root compile_commands.json: {destination}")


def configure_project(args: argparse.Namespace, build_after: bool) -> Path:
    project_dir = Path(args.project_dir).resolve()
    config = read_json(project_config_path(project_dir))
    build_type = args.build_type
    build_dir = project_dir / "build" / build_type
    env = os.environ.copy()
    load_vcvars_environment(env)
    ensure_ninja_on_path(env)

    if not args.skip_bundle:
        build_bundle(project_dir, config, env)

    migrate_cmake_generated_dir(project_dir)
    generate_bundle_header(project_dir, build_dir, config)
    generate_config_files(project_dir, build_dir, config)
    generate_conanfile(project_dir, config)

    conan = config.get("conan", {})
    profile = resolve_project_path(project_dir, conan.get("profile", "profiles/windows-msvc-static"))
    if profile is None or not profile.exists():
        raise RuntimeError(f"Conan profile was not found: {profile}")
    remote = args.remote or conan.get("remote") or DEFAULT_REMOTE

    run(
        [
            "conan",
            "install",
            str(project_dir),
            "-pr:a",
            str(profile),
            "-s:a",
            f"build_type={build_type}",
            "-r",
            str(remote),
            "--build=missing",
        ],
        cwd=project_dir,
        env=env,
    )

    toolchain = build_dir / "generators" / "conan_toolchain.cmake"
    if not toolchain.exists():
        raise RuntimeError(f"Conan toolchain file was not generated: {toolchain}")

    cmake = find_cmake()
    run(
        [
            cmake,
            "-S",
            str(project_dir),
            "-B",
            str(build_dir),
            "-G",
            "Ninja",
            f"-DCMAKE_BUILD_TYPE={build_type}",
            "-DCMAKE_EXPORT_COMPILE_COMMANDS=ON",
            f"-DCMAKE_TOOLCHAIN_FILE={toolchain}",
        ],
        cwd=project_dir,
        env=env,
    )
    sync_compile_commands(project_dir, build_dir, config)

    if build_after:
        run([cmake, "--build", str(build_dir)], cwd=project_dir, env=env)

    if args.export:
        export_project(args)
    return build_dir


def export_project(args: argparse.Namespace) -> None:
    project_dir = Path(args.project_dir).resolve()
    config = read_json(project_config_path(project_dir))
    build_type = args.build_type
    target = sanitize_identifier(config.get("target") or config.get("name") or "lynx_app")
    embed_bundle = bool(config.get("bundle", {}).get("embed_main_bundle", True))
    copy_icu = bool(config.get("runtime", {}).get("copy_icu", True))
    build_dir = project_dir / "build" / build_type
    exe = build_dir / f"{target}.exe"
    if not exe.exists():
        raise RuntimeError(f"Executable was not found: {exe}")
    export_dir = Path(args.export_dir).resolve() if args.export_dir else project_dir / "dist" / build_type
    if export_dir.exists():
        shutil.rmtree(export_dir)
    export_dir.mkdir(parents=True, exist_ok=True)
    shutil.copy2(exe, export_dir / exe.name)
    exported = [exe.name]

    runtime_assets = ["icudtl.dat", "lynx_core.js", "lynx_core_dev.js"]
    for name in runtime_assets:
        asset = build_dir / name
        if copy_icu and asset.exists():
            shutil.copy2(asset, export_dir / name)
            exported.append(name)
        elif copy_icu:
            log(f"warning: runtime asset was not found: {asset}")

    resources = build_dir / "resources"
    if not embed_bundle and resources.exists():
        shutil.copytree(resources, export_dir / "resources")
        exported.append("resources/")
    elif not embed_bundle:
        log(f"warning: external bundle resources were not found: {resources}")

    log(f"Exported project to: {export_dir}")
    for item in exported:
        log(f"  {item}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Create, configure, build, and export Conan-based Lynx static projects."
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    init_parser = subparsers.add_parser("init", help="Create a new Lynx project.")
    init_parser.add_argument("path", nargs="?", help="Project directory. Defaults to ./<project-name>.")
    init_parser.add_argument("--root", help="Create the project under this root directory.")
    init_parser.add_argument("--name", help="Project name. If omitted, the script prompts for it.")
    init_parser.add_argument("--force", action="store_true", help="Overwrite an existing generated project.")

    configure_parser = subparsers.add_parser("configure", help="Generate files, install Conan deps, and run CMake configure.")
    configure_parser.add_argument("project_dir", nargs="?", default=".")
    configure_parser.add_argument("--build-type", default="Release")
    configure_parser.add_argument("--remote")
    configure_parser.add_argument("--skip-bundle", action="store_true")
    configure_parser.add_argument("--export", action="store_true")
    configure_parser.add_argument("--export-dir")

    build_parser = subparsers.add_parser("build", help="Configure and build a Lynx project.")
    build_parser.add_argument("project_dir", nargs="?", default=".")
    build_parser.add_argument("--build-type", default="Release")
    build_parser.add_argument("--remote")
    build_parser.add_argument("--skip-bundle", action="store_true")
    build_parser.add_argument("--export", action="store_true")
    build_parser.add_argument("--export-dir")

    export_parser = subparsers.add_parser("export", help="Export an already built project.")
    export_parser.add_argument("project_dir", nargs="?", default=".")
    export_parser.add_argument("--build-type", default="Release")
    export_parser.add_argument("--export-dir")
    export_parser.set_defaults(export=True)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.command == "init":
        create_project(args)
    elif args.command == "configure":
        configure_project(args, build_after=False)
    elif args.command == "build":
        configure_project(args, build_after=True)
    elif args.command == "export":
        export_project(args)
    else:
        raise RuntimeError(f"Unknown command: {args.command}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(str(exc), file=sys.stderr)
        raise SystemExit(1)
