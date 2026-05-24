from __future__ import annotations

import os
from pathlib import Path

from conan import ConanFile
from conan.errors import ConanException, ConanInvalidConfiguration
from conan.tools.files import copy


class LynxlibRuntimeConan(ConanFile):
    name = "lynxlib-runtime"
    package_type = "build-scripts"
    settings = "os", "arch", "build_type"
    exports_sources = "cmake/lynxlib-runtime.cmake"
    no_copy_source = True

    def validate(self) -> None:
        if self.settings.os != "Windows":
            raise ConanInvalidConfiguration("lynxlib runtime package is currently built for Windows only.")
        if self.settings.arch != "x86_64":
            raise ConanInvalidConfiguration("lynxlib runtime package is currently built for Windows x86_64 only.")
        if self.settings.build_type != "Release":
            raise ConanInvalidConfiguration("lynxlib runtime package is exported from the Release GN output.")

    def _artifact_root(self) -> Path:
        override = os.environ.get("LYNXLIB_PACKAGE_OUT_DIR")
        if override:
            return Path(override).expanduser().resolve()
        return Path(self.source_folder).parent / "out" / "lynx" / "Prod"

    @staticmethod
    def _find_asset(artifact_root: Path, name: str) -> Path:
        candidates = [
            artifact_root / name,
            artifact_root / "lynx_core" / name,
            artifact_root / "lynx_explorer" / name,
        ]
        for candidate in candidates:
            if candidate.exists():
                return candidate
        return candidates[0]

    def package(self) -> None:
        artifact_root = self._artifact_root()
        icu_data = artifact_root / "icudtl.dat"
        if not icu_data.exists():
            raise ConanException(f"Missing Lynx ICU data file: {icu_data}")
        core_js = self._find_asset(artifact_root, "lynx_core.js")
        if not core_js.exists():
            raise ConanException(f"Missing Lynx core JS file: {core_js}")
        core_dev_js = self._find_asset(artifact_root, "lynx_core_dev.js")
        if not core_dev_js.exists():
            raise ConanException(f"Missing Lynx core dev JS file: {core_dev_js}")

        package_root = Path(self.package_folder)
        copy(self, "icudtl.dat", src=str(artifact_root), dst=str(package_root / "res"), keep_path=False)
        copy(self, "lynx_core.js", src=str(core_js.parent), dst=str(package_root / "res"), keep_path=False)
        copy(self, "lynx_core_dev.js", src=str(core_dev_js.parent), dst=str(package_root / "res"), keep_path=False)
        copy(
            self,
            "lynxlib-runtime.cmake",
            src=str(Path(self.source_folder) / "cmake"),
            dst=str(package_root / "lib" / "cmake" / "lynxlib-runtime"),
            keep_path=False,
        )

    def package_info(self) -> None:
        self.cpp_info.set_property("cmake_file_name", "lynxlib_runtime")
        self.cpp_info.set_property("cmake_target_name", "lynxlib_runtime::runtime")
        self.cpp_info.set_property(
            "cmake_build_modules",
            [os.path.join("lib", "cmake", "lynxlib-runtime", "lynxlib-runtime.cmake")],
        )
