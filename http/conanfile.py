from __future__ import annotations

import os

from conan import ConanFile
from conan.errors import ConanInvalidConfiguration
from conan.tools.cmake import CMake, CMakeDeps, CMakeToolchain, cmake_layout


class LynxlibHttpConan(ConanFile):
    name = "lynxlib-http"
    package_type = "static-library"
    settings = "os", "arch", "compiler", "build_type"
    exports_sources = "CMakeLists.txt", "include/*", "src/*"

    default_options = {
        "libcurl/*:shared": False,
        "libcurl/*:build_executable": False,
        "libcurl/*:with_ssl": "schannel",
        "libcurl/*:with_http": True,
        "libcurl/*:with_file": False,
        "libcurl/*:with_ftp": False,
        "libcurl/*:with_gopher": False,
        "libcurl/*:with_imap": False,
        "libcurl/*:with_ldap": False,
        "libcurl/*:with_mqtt": False,
        "libcurl/*:with_pop3": False,
        "libcurl/*:with_rtsp": False,
        "libcurl/*:with_smb": False,
        "libcurl/*:with_smtp": False,
        "libcurl/*:with_telnet": False,
        "libcurl/*:with_tftp": False,
        "libcurl/*:with_dict": False,
        "libcurl/*:with_libssh2": False,
        "libcurl/*:with_libidn": False,
        "libcurl/*:with_libpsl": False,
        "libcurl/*:with_nghttp2": False,
        "libcurl/*:with_zlib": True,
        "libcurl/*:with_brotli": False,
        "libcurl/*:with_zstd": False,
        "libcurl/*:with_c_ares": True,
        "libcurl/*:with_threaded_resolver": False,
        "libcurl/*:with_proxy": True,
        "libcurl/*:with_crypto_auth": True,
        "libcurl/*:with_ntlm": False,
        "libcurl/*:with_cookies": True,
        "libcurl/*:with_ipv6": True,
        "libcurl/*:with_docs": False,
        "libcurl/*:with_misc_docs": False,
        "libcurl/*:with_verbose_debug": False,
        "libcurl/*:with_verbose_strings": True,
        "libcurl/*:with_websockets": False,
        "c-ares/*:shared": False,
        "zlib/*:shared": False,
    }

    def requirements(self) -> None:
        self.requires(os.environ.get("LYNXLIB_HTTP_LYNXLIB_REF", "lynxlib/0.2.2@neuyan/stable"))
        self.requires(os.environ.get("LYNXLIB_HTTP_LIBCURL_REF", "libcurl/8.20.0"))

    def validate(self) -> None:
        if self.settings.os != "Windows":
            raise ConanInvalidConfiguration("lynxlib-http currently supports Windows only.")
        if self.settings.arch != "x86_64":
            raise ConanInvalidConfiguration("lynxlib-http currently supports Windows x86_64 only.")
        if self.settings.build_type != "Release":
            raise ConanInvalidConfiguration("lynxlib-http is packaged against the Release lynxlib archive.")
        if self.settings.compiler != "msvc":
            raise ConanInvalidConfiguration("lynxlib-http is built for the MSVC/clang-cl ABI.")

        cppstd = self.settings.get_safe("compiler.cppstd")
        if cppstd and int(str(cppstd).replace("gnu", "")) < 17:
            raise ConanInvalidConfiguration("lynxlib-http consumers must use at least C++17.")

        runtime = self.settings.get_safe("compiler.runtime")
        if runtime and runtime != "static":
            raise ConanInvalidConfiguration("lynxlib-http expects compiler.runtime=static.")

    def layout(self) -> None:
        cmake_layout(self)

    def generate(self) -> None:
        deps = CMakeDeps(self)
        deps.generate()

        toolchain = CMakeToolchain(self)
        toolchain.cache_variables["CMAKE_EXPORT_COMPILE_COMMANDS"] = "ON"
        toolchain.cache_variables["CMAKE_MSVC_RUNTIME_LIBRARY"] = "MultiThreaded$<$<CONFIG:Debug>:Debug>"
        toolchain.generate()

    def build(self) -> None:
        cmake = CMake(self)
        cmake.configure()
        cmake.build()

    def package(self) -> None:
        cmake = CMake(self)
        cmake.install()

    def package_info(self) -> None:
        self.cpp_info.set_property("cmake_file_name", "lynxlib_http")
        self.cpp_info.set_property("cmake_target_name", "lynxlib_http::lynxlib_http")
        self.cpp_info.libs = ["lynxlib_http"]
        self.cpp_info.requires = ["lynxlib::lynxlib", "libcurl::curl"]
