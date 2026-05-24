cmake_minimum_required(VERSION 3.23)

project(lynx_static_demo LANGUAGES CXX)

if(NOT WIN32)
  message(FATAL_ERROR "lynx_static_demo currently supports Windows only.")
endif()

find_package(lynxlib CONFIG REQUIRED)
find_package(lynxlib_runtime CONFIG REQUIRED)
find_package(lynxlib_http CONFIG REQUIRED)

set(LYNX_STATIC_DEMO_BUNDLE
    "${CMAKE_CURRENT_SOURCE_DIR}/bundle/dist/main.lynx.bundle"
    CACHE FILEPATH "Path to the prebuilt Lynx demo bundle")

if(NOT EXISTS "${LYNX_STATIC_DEMO_BUNDLE}")
  message(FATAL_ERROR
    "Demo bundle not found: ${LYNX_STATIC_DEMO_BUNDLE}\n"
    "Build or provide bundle/dist/main.lynx.bundle before configuring the standalone demo.")
endif()

add_executable(lynx_static_demo WIN32
  src/lynx_static_demo.cc)

target_compile_features(lynx_static_demo PRIVATE cxx_std_17)
target_compile_definitions(lynx_static_demo PRIVATE
  WIN32_LEAN_AND_MEAN
  NOMINMAX)
set_property(TARGET lynx_static_demo PROPERTY
  MSVC_RUNTIME_LIBRARY "MultiThreaded$<$<CONFIG:Debug>:Debug>")
target_link_libraries(lynx_static_demo PRIVATE
  lynxlib::lynxlib
  lynxlib_http::lynxlib_http)

if(MSVC)
  target_compile_options(lynx_static_demo PRIVATE /EHsc)
  target_link_options(lynx_static_demo PRIVATE "/INCLUDE:?SetupWeakNodeApiEnv@napi@primjs@@YAXXZ")
endif()

if(COMMAND lynxlib_copy_icu_data)
  lynxlib_copy_icu_data(lynx_static_demo)
elseif(COMMAND lynxlib_copy_runtime_assets)
  lynxlib_copy_runtime_assets(lynx_static_demo)
else()
  message(FATAL_ERROR "lynxlib runtime asset helper was not loaded from the Conan package.")
endif()

add_custom_target(lynx_static_demo_resources ALL
  COMMAND "${CMAKE_COMMAND}" -E make_directory
          "$<TARGET_FILE_DIR:lynx_static_demo>/resources/demo"
  COMMAND "${CMAKE_COMMAND}" -E copy_if_different
          "${LYNX_STATIC_DEMO_BUNDLE}"
          "$<TARGET_FILE_DIR:lynx_static_demo>/resources/demo/main.lynx.bundle"
  DEPENDS "${LYNX_STATIC_DEMO_BUNDLE}"
  COMMENT "Copying Lynx static demo bundle")

add_dependencies(lynx_static_demo lynx_static_demo_resources)
