from __future__ import annotations

import json
import os
import sys
from pathlib import Path

from lynxlib_common import is_windows, log, run


LLVM_COMPONENTS = [
    "Microsoft.VisualStudio.Component.VC.Llvm.Clang",
    "Microsoft.VisualStudio.Component.VC.Llvm.ClangToolset",
]


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


def llvm_bin(vs_root: Path) -> Path:
    return vs_root / "VC" / "Tools" / "Llvm" / "x64" / "bin"


def has_llvm_toolchain(vs_root: Path) -> bool:
    bin_dir = llvm_bin(vs_root)
    return (bin_dir / "clang-cl.exe").exists() and (bin_dir / "lld-link.exe").exists()


def main() -> int:
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

    raise RuntimeError(
        "Visual Studio LLVM/Clang toolset is missing. Install components:\n"
        + "\n".join(f"  {component}" for component in LLVM_COMPONENTS)
    )


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(str(exc), file=sys.stderr)
        raise SystemExit(1)
