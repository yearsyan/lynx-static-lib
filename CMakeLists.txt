cmake_minimum_required(VERSION 3.20)

project(lynxlib_official_sdk LANGUAGES CXX)

if(NOT WIN32)
  message(FATAL_ERROR "This Lynx embedder package currently builds the demo on Windows only.")
endif()

find_package(Python3 REQUIRED COMPONENTS Interpreter)

set(LYNXLIB_LYNX_ROOT
    "${CMAKE_CURRENT_SOURCE_DIR}/third_party/lynx"
    CACHE PATH "Path to the official Lynx source tree")

set(LYNXLIB_LYNX_OUT_DIR
    "${CMAKE_CURRENT_SOURCE_DIR}/out/lynx/Default"
    CACHE PATH "GN output directory for official Lynx build artifacts")

set(LYNXLIB_SCRIPT
    "${CMAKE_CURRENT_SOURCE_DIR}/scripts/build_lynx.py")
set(LYNXLIB_SYNC_SCRIPT
    "${CMAKE_CURRENT_SOURCE_DIR}/scripts/sync_lynx_deps.py")
set(LYNXLIB_DEMO_BUNDLE_SCRIPT
    "${CMAKE_CURRENT_SOURCE_DIR}/scripts/build_demo_bundle.py")

add_custom_target(lynx_official_deps
  COMMAND "${Python3_EXECUTABLE}" "${LYNXLIB_SYNC_SCRIPT}"
          --lynx-root "${LYNXLIB_LYNX_ROOT}"
  WORKING_DIRECTORY "${CMAKE_CURRENT_SOURCE_DIR}"
  USES_TERMINAL
  COMMENT "Synchronizing pinned official Lynx build dependencies")

add_custom_target(lynx_official_sdk
  COMMAND "${Python3_EXECUTABLE}" "${LYNXLIB_SCRIPT}"
          --target sdk
          --lynx-root "${LYNXLIB_LYNX_ROOT}"
          --out-dir "${LYNXLIB_LYNX_OUT_DIR}"
          --skip-deps
  WORKING_DIRECTORY "${CMAKE_CURRENT_SOURCE_DIR}"
  USES_TERMINAL
  COMMENT "Building the official Lynx Windows SDK package")

add_custom_target(lynx_static_archive
  COMMAND "${Python3_EXECUTABLE}" "${LYNXLIB_SCRIPT}"
          --target static
          --lynx-root "${LYNXLIB_LYNX_ROOT}"
          --out-dir "${LYNXLIB_LYNX_OUT_DIR}"
          --skip-deps
  WORKING_DIRECTORY "${CMAKE_CURRENT_SOURCE_DIR}"
  USES_TERMINAL
  COMMENT "Building official Lynx objects and archiving them as lynx_static.lib")

add_custom_target(lynx_explorer_demo
  COMMAND "${Python3_EXECUTABLE}" "${LYNXLIB_SCRIPT}"
          --target explorer
          --lynx-root "${LYNXLIB_LYNX_ROOT}"
          --out-dir "${LYNXLIB_LYNX_OUT_DIR}"
          --skip-deps
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
  COMMAND "${Python3_EXECUTABLE}" "${LYNXLIB_DEMO_BUNDLE_SCRIPT}"
          --bundle-root "${CMAKE_CURRENT_SOURCE_DIR}/demo/bundle"
          --lynx-root "${LYNXLIB_LYNX_ROOT}"
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
