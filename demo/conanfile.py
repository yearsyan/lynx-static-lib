from __future__ import annotations

from conan import ConanFile
from conan.tools.cmake import CMakeDeps, CMakeToolchain, cmake_layout


class LynxStaticDemoConan(ConanFile):
    name = "lynx_static_demo"
    version = "0.1.0"
    settings = "os", "arch", "compiler", "build_type"

    def requirements(self) -> None:
        self.requires("lynxlib/0.1.1@neuyan/stable")
        self.requires("lynxlib-runtime/0.1.0@neuyan/stable")

    def layout(self) -> None:
        cmake_layout(self)

    def generate(self) -> None:
        deps = CMakeDeps(self)
        deps.generate()

        toolchain = CMakeToolchain(self)
        toolchain.cache_variables["CMAKE_EXPORT_COMPILE_COMMANDS"] = "ON"
        toolchain.cache_variables["CMAKE_MSVC_RUNTIME_LIBRARY"] = "MultiThreaded$<$<CONFIG:Debug>:Debug>"
        toolchain.generate()
