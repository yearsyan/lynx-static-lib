cmake_minimum_required(VERSION 3.23)

project(lynxlib_http_test_package LANGUAGES CXX)

find_package(lynxlib_http CONFIG REQUIRED)

add_executable(lynxlib_http_test_package
  test_package.cc)
target_compile_features(lynxlib_http_test_package PRIVATE cxx_std_17)
target_link_libraries(lynxlib_http_test_package
  PRIVATE lynxlib_http::lynxlib_http)

if(MSVC)
  target_compile_options(lynxlib_http_test_package PRIVATE /EHsc)
endif()
