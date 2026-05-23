from __future__ import annotations

import os
import shutil
import sys
import zipfile
from pathlib import Path

from lynxlib_common import download_file, is_macos, is_windows, log, run, sha256_file


PINNED_CMAKE_VERSION = "3.31.12"
PINNED_CMAKE_PACKAGE = f"cmake-{PINNED_CMAKE_VERSION}-windows-x86_64.zip"
PINNED_CMAKE_URL = (
    f"https://github.com/Kitware/CMake/releases/download/v{PINNED_CMAKE_VERSION}/{PINNED_CMAKE_PACKAGE}"
)
PINNED_CMAKE_SHA256 = "0c4baa40f28b3f8225eb3fdf6946c987b4fe901403b4eaf2fbbd9378100aaa0c"


def candidate_cmake_paths() -> list[Path]:
    candidates: list[Path] = []
    found = shutil.which("cmake")
    if found:
        candidates.append(Path(found))

    if is_windows():
        for env_name in ["ProgramFiles", "ProgramFiles(x86)", "LOCALAPPDATA"]:
            root = os.environ.get(env_name)
            if root:
                candidates.append(Path(root) / "CMake" / "bin" / "cmake.exe")
        vs_root = Path("C:/Program Files/Microsoft Visual Studio/2022")
        for edition in ["BuildTools", "Community", "Professional", "Enterprise"]:
            candidates.append(
                vs_root
                / edition
                / "Common7"
                / "IDE"
                / "CommonExtensions"
                / "Microsoft"
                / "CMake"
                / "CMake"
                / "bin"
                / "cmake.exe"
            )
    elif is_macos():
        candidates.extend(
            [
                Path("/Applications/CMake.app/Contents/bin/cmake"),
                Path("/opt/homebrew/bin/cmake"),
                Path("/usr/local/bin/cmake"),
            ]
        )
    return candidates


def install_pinned_cmake() -> Path:
    if not is_windows():
        raise RuntimeError("cmake was not found in PATH. Install CMake for this platform and rerun the build.")

    tool_root = (
        Path(os.environ["RUNNER_TOOL_CACHE"]) / "lynxlib"
        if os.environ.get("RUNNER_TOOL_CACHE")
        else Path(os.environ.get("RUNNER_TEMP", Path.cwd() / "third_party" / "_cache")) / "lynxlib-tools"
    )
    extract_root = tool_root / f"cmake-{PINNED_CMAKE_VERSION}-windows-x86_64"
    cmake = extract_root / "bin" / "cmake.exe"
    if cmake.exists():
        return cmake

    tool_root.mkdir(parents=True, exist_ok=True)
    archive = tool_root / PINNED_CMAKE_PACKAGE
    if not archive.exists():
        log(f"Downloading pinned CMake {PINNED_CMAKE_VERSION} from {PINNED_CMAKE_URL}")
        download_file(PINNED_CMAKE_URL, archive)

    actual_hash = sha256_file(archive)
    if actual_hash != PINNED_CMAKE_SHA256:
        raise RuntimeError(f"CMake archive SHA-256 mismatch. Expected {PINNED_CMAKE_SHA256}, got {actual_hash}.")

    with zipfile.ZipFile(archive) as file:
        file.extractall(tool_root)
    if not cmake.exists():
        raise RuntimeError(f"Pinned CMake archive did not contain the expected executable: {cmake}")
    return cmake


def find_cmake() -> Path:
    for candidate in candidate_cmake_paths():
        if candidate.exists():
            return candidate
    return install_pinned_cmake()


def main() -> int:
    cmake = find_cmake()
    log(f"Using CMake: {cmake}")
    completed = run([cmake, *sys.argv[1:]], check=False)
    return completed.returncode


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(str(exc), file=sys.stderr)
        raise SystemExit(1)
