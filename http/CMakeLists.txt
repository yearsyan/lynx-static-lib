cmake_minimum_required(VERSION 3.23)

project(lynxlib_http LANGUAGES CXX)

if(NOT WIN32)
  message(FATAL_ERROR "lynxlib_http currently supports Windows only.")
endif()

find_package(lynxlib CONFIG REQUIRED)
find_package(CURL CONFIG REQUIRED)

add_library(lynxlib_http STATIC
  src/curl_http_service.cc)
add_library(lynxlib_http::lynxlib_http ALIAS lynxlib_http)

target_compile_features(lynxlib_http PUBLIC cxx_std_17)
target_include_directories(lynxlib_http
  PUBLIC
    $<BUILD_INTERFACE:${CMAKE_CURRENT_SOURCE_DIR}/include>
    $<INSTALL_INTERFACE:include>)
target_compile_definitions(lynxlib_http
  PRIVATE
    WIN32_LEAN_AND_MEAN
    NOMINMAX)
target_link_libraries(lynxlib_http
  PUBLIC
    lynxlib::lynxlib
    CURL::libcurl)

set_property(TARGET lynxlib_http PROPERTY
  MSVC_RUNTIME_LIBRARY "MultiThreaded$<$<CONFIG:Debug>:Debug>")

if(MSVC)
  target_compile_options(lynxlib_http PRIVATE /EHsc)
endif()

include(GNUInstallDirs)

install(TARGETS lynxlib_http
  ARCHIVE DESTINATION ${CMAKE_INSTALL_LIBDIR}
  LIBRARY DESTINATION ${CMAKE_INSTALL_LIBDIR}
  RUNTIME DESTINATION ${CMAKE_INSTALL_BINDIR})
install(DIRECTORY include/
  DESTINATION ${CMAKE_INSTALL_INCLUDEDIR})
