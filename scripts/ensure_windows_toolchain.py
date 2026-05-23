from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

from lynxlib_common import is_windows, log, run


LLVM_COMPONENT = "Microsoft.VisualStudio.ComponentGroup.NativeDesktop.Llvm.Clang"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Validate the Windows Visual Studio LLVM toolchain.")
    parser.add_argument(
        "--install-missing",
        action="store_true",
        help="Use Visual Studio Installer to add the LLVM/Clang component when it is missing.",
    )
    return parser.parse_args()


def program_files_roots() -> list[Path]:
    roots = []
    for env_name in ["ProgramFiles", "ProgramFiles(x86)"]:
        value = os.environ.get(env_name)
        if value:
            roots.append(Path(value))
    return roots


def find_vswhere() -> Path | None:
    for root in program_files_roots():
        candidate = root / "Microsoft Visual Studio" / "Installer" / "vswhere.exe"
        if candidate.exists():
            return candidate
    return None


def find_vs_installer() -> Path | None:
    for root in program_files_roots():
        candidate = root / "Microsoft Visual Studio" / "Installer" / "vs_installer.exe"
        if candidate.exists():
            return candidate
    return None


def visual_studio_installations() -> list[Path]:
    installations: list[Path] = []
    vswhere = find_vswhere()
    if vswhere:
        result = run([vswhere, "-all", "-products", "*", "-format", "json"], quiet=True)
        for entry in json.loads(result.stdout or "[]"):
            path = Path(entry.get("installationPath", ""))
            if path.exists():
                installations.append(path)

    for root in program_files_roots():
        base = root / "Microsoft Visual Studio" / "2022"
        for edition in ["BuildTools", "Community", "Professional", "Enterprise"]:
            path = base / edition
            if path.exists() and path not in installations:
                installations.append(path)
    return installations


def llvm_bin(vs_root: Path) -> Path:
    return vs_root / "VC" / "Tools" / "Llvm" / "x64" / "bin"


def has_llvm_toolchain(vs_root: Path) -> bool:
    bin_dir = llvm_bin(vs_root)
    return (bin_dir / "clang-cl.exe").exists() and (bin_dir / "lld-link.exe").exists()


def install_llvm_component(vs_root: Path) -> None:
    installer = find_vs_installer()
    if not installer:
        raise RuntimeError("Visual Studio Installer was not found; cannot install missing LLVM/Clang component.")

    log(f"Installing Visual Studio component {LLVM_COMPONENT} into {vs_root}")
    run(
        [
            installer,
            "modify",
            "--installPath",
            vs_root,
            "--add",
            LLVM_COMPONENT,
            "--quiet",
            "--norestart",
            "--wait",
        ]
    )


def main() -> int:
    args = parse_args()
    if not is_windows():
        log("Windows toolchain check skipped on non-Windows host.")
        return 0

    installations = visual_studio_installations()
    if not installations:
        raise RuntimeError("Visual Studio 2022 was not found. Install VS 2022 Build Tools with C++ support.")

    for installation in installations:
        if has_llvm_toolchain(installation):
            log(f"Using Visual Studio LLVM toolchain: {llvm_bin(installation)}")
            return 0

    if not args.install_missing:
        raise RuntimeError(
            "Visual Studio LLVM/Clang toolset is missing. Install component:\n"
            f"  {LLVM_COMPONENT}"
        )

    install_llvm_component(installations[0])
    for installation in visual_studio_installations():
        if has_llvm_toolchain(installation):
            log(f"Using Visual Studio LLVM toolchain: {llvm_bin(installation)}")
            return 0

    raise RuntimeError(
        "Visual Studio Installer completed, but clang-cl.exe and lld-link.exe are still missing under VC/Tools/Llvm."
    )


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(str(exc), file=sys.stderr)
        raise SystemExit(1)
