cmake_minimum_required(VERSION 3.20)

project(lynxlib_official_sdk LANGUAGES CXX)

if(NOT WIN32)
  message(FATAL_ERROR "This Lynx embedder package currently supports Windows only.")
endif()

set(LYNXLIB_LYNX_ROOT
    "${CMAKE_CURRENT_SOURCE_DIR}/third_party/lynx"
    CACHE PATH "Path to the official Lynx source tree")

set(LYNXLIB_LYNX_OUT_DIR
    "${CMAKE_CURRENT_SOURCE_DIR}/out/lynx/Default"
    CACHE PATH "GN output directory for official Lynx build artifacts")

find_program(LYNXLIB_POWERSHELL pwsh)
if(NOT LYNXLIB_POWERSHELL)
  find_program(LYNXLIB_POWERSHELL powershell)
endif()
if(NOT LYNXLIB_POWERSHELL)
  message(FATAL_ERROR "PowerShell is required to drive the official Lynx Windows build.")
endif()

set(LYNXLIB_SCRIPT
    "${CMAKE_CURRENT_SOURCE_DIR}/scripts/Build-LynxWindows.ps1")
set(LYNXLIB_SYNC_SCRIPT
    "${CMAKE_CURRENT_SOURCE_DIR}/scripts/Sync-LynxDeps.ps1")
set(LYNXLIB_DEMO_BUNDLE_SCRIPT
    "${CMAKE_CURRENT_SOURCE_DIR}/scripts/Build-DemoBundle.ps1")

add_custom_target(lynx_official_deps
  COMMAND "${LYNXLIB_POWERSHELL}" -NoProfile -ExecutionPolicy Bypass
          -File "${LYNXLIB_SYNC_SCRIPT}"
          -LynxRoot "${LYNXLIB_LYNX_ROOT}"
  WORKING_DIRECTORY "${CMAKE_CURRENT_SOURCE_DIR}"
  USES_TERMINAL
  COMMENT "Synchronizing pinned official Lynx build dependencies")

add_custom_target(lynx_official_sdk
  COMMAND "${LYNXLIB_POWERSHELL}" -NoProfile -ExecutionPolicy Bypass
          -File "${LYNXLIB_SCRIPT}"
          -Target sdk
          -LynxRoot "${LYNXLIB_LYNX_ROOT}"
          -OutDir "${LYNXLIB_LYNX_OUT_DIR}"
          -SkipDeps
  WORKING_DIRECTORY "${CMAKE_CURRENT_SOURCE_DIR}"
  USES_TERMINAL
  COMMENT "Building the official Lynx Windows SDK package")

add_custom_target(lynx_static_archive
  COMMAND "${LYNXLIB_POWERSHELL}" -NoProfile -ExecutionPolicy Bypass
          -File "${LYNXLIB_SCRIPT}"
          -Target static
          -LynxRoot "${LYNXLIB_LYNX_ROOT}"
          -OutDir "${LYNXLIB_LYNX_OUT_DIR}"
          -SkipDeps
  WORKING_DIRECTORY "${CMAKE_CURRENT_SOURCE_DIR}"
  USES_TERMINAL
  COMMENT "Building official Lynx objects and archiving them as lynx_static.lib")

add_custom_target(lynx_explorer_demo
  COMMAND "${LYNXLIB_POWERSHELL}" -NoProfile -ExecutionPolicy Bypass
          -File "${LYNXLIB_SCRIPT}"
          -Target explorer
          -LynxRoot "${LYNXLIB_LYNX_ROOT}"
          -OutDir "${LYNXLIB_LYNX_OUT_DIR}"
          -SkipDeps
  WORKING_DIRECTORY "${CMAKE_CURRENT_SOURCE_DIR}"
  USES_TERMINAL
  COMMENT "Building the official Windows Lynx Explorer demo")

set(LYNXLIB_STATIC_LIBRARY "${LYNXLIB_LYNX_OUT_DIR}/lynx_static.lib")
set(LYNXLIB_STATIC_FORCE_INCLUDE_SYMBOLS
  # This constructor-only object installs the weak N-API host. A normal static
  # archive link will not pull it unless a root symbol is provided.
  "?SetupWeakNodeApiEnv@napi@primjs@@YAXXZ")
set(LYNXLIB_DEMO_BUNDLE_SOURCE
  "${CMAKE_CURRENT_SOURCE_DIR}/demo/bundle/dist/main.lynx.bundle")

add_custom_target(lynx_demo_bundle
  COMMAND "${LYNXLIB_POWERSHELL}" -NoProfile -ExecutionPolicy Bypass
          -File "${LYNXLIB_DEMO_BUNDLE_SCRIPT}"
          -BundleRoot "${CMAKE_CURRENT_SOURCE_DIR}/demo/bundle"
          -LynxRoot "${LYNXLIB_LYNX_ROOT}"
  BYPRODUCTS "${LYNXLIB_DEMO_BUNDLE_SOURCE}"
  WORKING_DIRECTORY "${CMAKE_CURRENT_SOURCE_DIR}"
  USES_TERMINAL
  COMMENT "Building the local Lynx demo bundle")

add_executable(lynx_static_demo WIN32
  demo/src/lynx_static_demo.cc)
add_dependencies(lynx_static_demo lynx_static_archive lynx_demo_bundle)
target_compile_features(lynx_static_demo PRIVATE cxx_std_17)
target_compile_definitions(lynx_static_demo PRIVATE
  WIN32_LEAN_AND_MEAN
  NOMINMAX
  LYNX_STATIC_LINK)
target_include_directories(lynx_static_demo PRIVATE
  "${LYNXLIB_LYNX_OUT_DIR}/include")
set_property(TARGET lynx_static_demo PROPERTY
  MSVC_RUNTIME_LIBRARY "MultiThreaded$<$<CONFIG:Debug>:Debug>")
target_link_libraries(lynx_static_demo PRIVATE
  "${LYNXLIB_STATIC_LIBRARY}"
  user32
  gdi32
  shell32
  advapi32
  ole32
  oleaut32
  imm32
  version
  winmm
  shlwapi
  dwmapi
  dxgi
  d3d11
  d3d9
  d3dcompiler
  dxguid
  opengl32
  fontsub
  usp10
  comctl32
  ws2_32
  crypt32
  bcrypt
  rpcrt4
  iphlpapi
  psapi
  userenv
  setupapi)
foreach(symbol IN LISTS LYNXLIB_STATIC_FORCE_INCLUDE_SYMBOLS)
  target_link_options(lynx_static_demo PRIVATE "/INCLUDE:${symbol}")
endforeach()

add_custom_command(TARGET lynx_static_demo POST_BUILD
  COMMAND "${CMAKE_COMMAND}" -E make_directory
          "$<TARGET_FILE_DIR:lynx_static_demo>/resources/demo"
  COMMAND "${CMAKE_COMMAND}" -E copy_if_different
          "${LYNXLIB_DEMO_BUNDLE_SOURCE}"
          "$<TARGET_FILE_DIR:lynx_static_demo>/resources/demo/main.lynx.bundle"
  COMMAND "${CMAKE_COMMAND}" -E copy_if_different
          "${LYNXLIB_LYNX_OUT_DIR}/icudtl.dat"
          "$<TARGET_FILE_DIR:lynx_static_demo>/icudtl.dat"
  COMMENT "Copying Lynx static demo runtime assets")

add_custom_target(lynx_all
  DEPENDS lynx_official_sdk lynx_static_archive lynx_static_demo lynx_explorer_demo)
