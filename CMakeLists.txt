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
    "${CMAKE_CURRENT_SOURCE_DIR}/out/lynx/Prod"
    CACHE PATH "GN output directory for official Lynx build artifacts")
set(LYNXLIB_LYNX_PROD_OUT_DIR
    "${CMAKE_CURRENT_SOURCE_DIR}/out/lynx/Prod"
    CACHE PATH "GN output directory for the production Lynx static build")
set(LYNXLIB_LYNX_DEV_OUT_DIR
    "${CMAKE_CURRENT_SOURCE_DIR}/out/lynx/Dev"
    CACHE PATH "GN output directory for the development Lynx static build")

set(LYNXLIB_SCRIPT
    "${CMAKE_CURRENT_SOURCE_DIR}/scripts/build_lynx.py")
set(LYNXLIB_SYNC_SCRIPT
    "${CMAKE_CURRENT_SOURCE_DIR}/scripts/sync_lynx_deps.py")
set(LYNXLIB_CONAN_SCRIPT
    "${CMAKE_CURRENT_SOURCE_DIR}/scripts/package_conan.py")
set(LYNXLIB_HTTP_CONAN_SCRIPT
    "${CMAKE_CURRENT_SOURCE_DIR}/scripts/package_http_conan.py")

set(LYNXLIB_CONAN_VERSION "0.2.2" CACHE STRING "Conan package version for lynxlib")
set(LYNXLIB_CONAN_USER "neuyan" CACHE STRING "Conan package user for lynxlib")
set(LYNXLIB_CONAN_CHANNEL "stable" CACHE STRING "Conan package channel for lynxlib")
set(LYNXLIB_CONAN_REMOTE "neuyan" CACHE STRING "Conan remote used when uploading lynxlib")
set(LYNXLIB_BUILD_FLAVOR "prod" CACHE STRING "Lynx static package flavor: prod or dev")
set_property(CACHE LYNXLIB_BUILD_FLAVOR PROPERTY STRINGS prod dev)

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
          --flavor "${LYNXLIB_BUILD_FLAVOR}"
          --skip-deps
  WORKING_DIRECTORY "${CMAKE_CURRENT_SOURCE_DIR}"
  USES_TERMINAL
  COMMENT "Building official Lynx objects and archiving them as lynx_static.lib")

add_custom_target(lynx_static_archive_prod
  COMMAND "${Python3_EXECUTABLE}" "${LYNXLIB_SCRIPT}"
          --target static
          --lynx-root "${LYNXLIB_LYNX_ROOT}"
          --out-dir "${LYNXLIB_LYNX_PROD_OUT_DIR}"
          --flavor prod
          --skip-deps
  WORKING_DIRECTORY "${CMAKE_CURRENT_SOURCE_DIR}"
  USES_TERMINAL
  COMMENT "Building production lynx_static.lib with embedded release core JS")

add_custom_target(lynx_static_archive_dev
  COMMAND "${Python3_EXECUTABLE}" "${LYNXLIB_SCRIPT}"
          --target static
          --lynx-root "${LYNXLIB_LYNX_ROOT}"
          --out-dir "${LYNXLIB_LYNX_DEV_OUT_DIR}"
          --flavor dev
          --skip-deps
  WORKING_DIRECTORY "${CMAKE_CURRENT_SOURCE_DIR}"
  USES_TERMINAL
  COMMENT "Building development lynx_static.lib with embedded dev core JS and inspector")

add_custom_target(lynx_explorer_demo
  COMMAND "${Python3_EXECUTABLE}" "${LYNXLIB_SCRIPT}"
          --target explorer
          --lynx-root "${LYNXLIB_LYNX_ROOT}"
          --out-dir "${LYNXLIB_LYNX_OUT_DIR}"
          --skip-deps
  WORKING_DIRECTORY "${CMAKE_CURRENT_SOURCE_DIR}"
  USES_TERMINAL
  COMMENT "Building the official Windows Lynx Explorer demo")

add_custom_target(lynx_static_conan_export
  COMMAND "${Python3_EXECUTABLE}" "${LYNXLIB_CONAN_SCRIPT}"
          --skip-build
          --version "${LYNXLIB_CONAN_VERSION}"
          --user "${LYNXLIB_CONAN_USER}"
          --channel "${LYNXLIB_CONAN_CHANNEL}"
          --remote "${LYNXLIB_CONAN_REMOTE}"
          --out-dir "${LYNXLIB_LYNX_OUT_DIR}"
          --flavor "${LYNXLIB_BUILD_FLAVOR}"
          --library-only
  DEPENDS lynx_static_archive
  WORKING_DIRECTORY "${CMAKE_CURRENT_SOURCE_DIR}"
  USES_TERMINAL
  COMMENT "Exporting lynx_static.lib as a local Conan package")

add_custom_target(lynx_static_conan_upload
  COMMAND "${Python3_EXECUTABLE}" "${LYNXLIB_CONAN_SCRIPT}"
          --skip-build
          --upload
          --version "${LYNXLIB_CONAN_VERSION}"
          --user "${LYNXLIB_CONAN_USER}"
          --channel "${LYNXLIB_CONAN_CHANNEL}"
          --remote "${LYNXLIB_CONAN_REMOTE}"
          --out-dir "${LYNXLIB_LYNX_OUT_DIR}"
          --flavor "${LYNXLIB_BUILD_FLAVOR}"
          --library-only
  DEPENDS lynx_static_archive
  WORKING_DIRECTORY "${CMAKE_CURRENT_SOURCE_DIR}"
  USES_TERMINAL
  COMMENT "Uploading lynx_static.lib Conan package to the configured remote")

add_custom_target(lynx_http_conan_create
  COMMAND "${Python3_EXECUTABLE}" "${LYNXLIB_HTTP_CONAN_SCRIPT}"
          --version "${LYNXLIB_CONAN_VERSION}"
          --user "${LYNXLIB_CONAN_USER}"
          --channel "${LYNXLIB_CONAN_CHANNEL}"
          --remote "${LYNXLIB_CONAN_REMOTE}"
          --lynxlib-flavor "${LYNXLIB_BUILD_FLAVOR}"
  DEPENDS lynx_static_conan_export
  WORKING_DIRECTORY "${CMAKE_CURRENT_SOURCE_DIR}"
  USES_TERMINAL
  COMMENT "Creating the lynxlib-http Conan package")

add_custom_target(lynx_http_conan_upload
  COMMAND "${Python3_EXECUTABLE}" "${LYNXLIB_HTTP_CONAN_SCRIPT}"
          --upload
          --version "${LYNXLIB_CONAN_VERSION}"
          --user "${LYNXLIB_CONAN_USER}"
          --channel "${LYNXLIB_CONAN_CHANNEL}"
          --remote "${LYNXLIB_CONAN_REMOTE}"
          --lynxlib-flavor "${LYNXLIB_BUILD_FLAVOR}"
  DEPENDS lynx_static_conan_export
  WORKING_DIRECTORY "${CMAKE_CURRENT_SOURCE_DIR}"
  USES_TERMINAL
  COMMENT "Uploading the lynxlib-http Conan package to the configured remote")

add_custom_target(lynx_all
  DEPENDS lynx_official_sdk lynx_static_archive lynx_explorer_demo)
