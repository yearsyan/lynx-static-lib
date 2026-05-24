from __future__ import annotations

import os
from pathlib import Path

from conan import ConanFile
from conan.errors import ConanException, ConanInvalidConfiguration
from conan.tools.files import copy


class LynxlibConan(ConanFile):
    name = "lynxlib"
    package_type = "static-library"
    settings = "os", "arch", "compiler", "build_type"
    no_copy_source = True

    def validate(self) -> None:
        if self.settings.os != "Windows":
            raise ConanInvalidConfiguration("lynxlib static package is currently built for Windows only.")
        if self.settings.arch != "x86_64":
            raise ConanInvalidConfiguration("lynxlib static package is currently built for Windows x86_64 only.")
        if self.settings.build_type != "Release":
            raise ConanInvalidConfiguration("lynxlib static package is exported from the Release GN output.")
        if self.settings.compiler != "msvc":
            raise ConanInvalidConfiguration("lynxlib static package is built with the MSVC/clang-cl ABI.")

        cppstd = self.settings.get_safe("compiler.cppstd")
        if cppstd and int(str(cppstd).replace("gnu", "")) < 17:
            raise ConanInvalidConfiguration("lynxlib consumers must use at least C++17.")

        runtime = self.settings.get_safe("compiler.runtime")
        if runtime and runtime != "static":
            raise ConanInvalidConfiguration("lynxlib static package expects compiler.runtime=static.")

    def _artifact_root(self) -> Path:
        override = os.environ.get("LYNXLIB_PACKAGE_OUT_DIR")
        if override:
            return Path(override).expanduser().resolve()
        return Path(self.source_folder) / "out" / "lynx" / "Default"

    def package(self) -> None:
        artifact_root = self._artifact_root()
        include_dir = artifact_root / "include"
        static_lib = artifact_root / "lynx_static.lib"

        missing = [path for path in [include_dir, static_lib] if not path.exists()]
        if missing:
            formatted = "\n  ".join(str(path) for path in missing)
            raise ConanException(f"Missing lynxlib package artifact(s):\n  {formatted}")

        package_root = Path(self.package_folder)
        copy(self, "*", src=str(include_dir), dst=str(package_root / "include"))
        copy(self, "lynx_static.lib", src=str(artifact_root), dst=str(package_root / "lib"), keep_path=False)

    def package_info(self) -> None:
        self.cpp_info.set_property("cmake_file_name", "lynxlib")
        self.cpp_info.set_property("cmake_target_name", "lynxlib::lynxlib")

        self.cpp_info.libs = ["lynx_static"]
        self.cpp_info.includedirs = ["include"]
        self.cpp_info.libdirs = ["lib"]
        self.cpp_info.defines = ["LYNX_STATIC_LINK"]
        self.cpp_info.exelinkflags = ["/INCLUDE:?SetupWeakNodeApiEnv@napi@primjs@@YAXXZ"]
        self.cpp_info.sharedlinkflags = ["/INCLUDE:?SetupWeakNodeApiEnv@napi@primjs@@YAXXZ"]
        self.cpp_info.system_libs = [
            "user32",
            "gdi32",
            "shell32",
            "advapi32",
            "ole32",
            "oleaut32",
            "imm32",
            "version",
            "winmm",
            "shlwapi",
            "dwmapi",
            "dxgi",
            "d3d11",
            "d3d9",
            "d3dcompiler",
            "dxguid",
            "opengl32",
            "fontsub",
            "usp10",
            "comctl32",
            "ws2_32",
            "crypt32",
            "bcrypt",
            "rpcrt4",
            "iphlpapi",
            "psapi",
            "userenv",
            "setupapi",
        ]
