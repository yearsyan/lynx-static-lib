from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

from lynxlib_common import is_windows, log, run


LLVM_COMPONENTS = [
    "Microsoft.VisualStudio.Component.VC.Llvm.Clang",
    "Microsoft.VisualStudio.Component.VC.Llvm.ClangToolset",
]


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


def vswhere_entries() -> list[dict]:
    vswhere = find_vswhere()
    if not vswhere:
        return []
    result = run([vswhere, "-all", "-products", "*", "-format", "json"], quiet=True)
    return json.loads(result.stdout or "[]")


def visual_studio_installations() -> list[Path]:
    installations: list[Path] = []
    entries = vswhere_entries()
    for entry in entries:
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


def find_setup_engine(vs_root: Path) -> Path | None:
    for entry in vswhere_entries():
        path = Path(entry.get("installationPath", ""))
        if path.resolve() != vs_root.resolve():
            continue
        setup = Path(entry.get("properties", {}).get("setupEngineFilePath", ""))
        if setup.exists():
            return setup

    for root in program_files_roots():
        candidate = root / "Microsoft Visual Studio" / "Installer" / "setup.exe"
        if candidate.exists():
            return candidate

    installer = find_vs_installer()
    if installer:
        return installer
    return None


def llvm_bin(vs_root: Path) -> Path:
    return vs_root / "VC" / "Tools" / "Llvm" / "x64" / "bin"


def has_llvm_toolchain(vs_root: Path) -> bool:
    bin_dir = llvm_bin(vs_root)
    return (bin_dir / "clang-cl.exe").exists() and (bin_dir / "lld-link.exe").exists()


def install_llvm_component(vs_root: Path) -> None:
    setup = find_setup_engine(vs_root)
    if not setup:
        raise RuntimeError("Visual Studio Installer was not found; cannot install missing LLVM/Clang component.")

    log(f"Installing Visual Studio LLVM components into {vs_root}")
    command: list[str | Path] = [setup, "modify", "--installPath", vs_root]
    for component in LLVM_COMPONENTS:
        command.extend(["--add", component])
    command.extend(["--quiet", "--norestart"])

    result = run(command, check=False)
    if result.returncode not in (0, 3010):
        raise RuntimeError(f"Visual Studio Installer failed with exit code {result.returncode}.")


def wait_for_llvm_toolchain(vs_root: Path, timeout_seconds: int = 600) -> bool:
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        if has_llvm_toolchain(vs_root):
            return True
        time.sleep(10)
    return has_llvm_toolchain(vs_root)


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
            + "\n".join(f"  {component}" for component in LLVM_COMPONENTS)
        )

    install_llvm_component(installations[0])
    for installation in visual_studio_installations():
        if wait_for_llvm_toolchain(installation):
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
