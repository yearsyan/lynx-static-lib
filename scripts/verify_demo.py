from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path

from build_lynx import find_msvc_tool
from lynxlib_common import REPO_ROOT, is_windows, log, run


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Verify the Lynx static demo executable.")
    parser.add_argument(
        "--exe",
        default=REPO_ROOT / "build" / "cmake-driver" / "Release" / "lynx_static_demo.exe",
        type=Path,
    )
    parser.add_argument("--smoke-seconds", default=5, type=int)
    parser.add_argument("--skip-smoke", action="store_true")
    return parser.parse_args()


def verify_static_link(exe: Path) -> None:
    if not is_windows():
        raise RuntimeError("Static dependency verification currently uses dumpbin.exe and is Windows-only.")

    dumpbin = find_msvc_tool("dumpbin.exe", os.environ.copy())
    if not dumpbin:
        raise RuntimeError("dumpbin.exe was not found in the Visual Studio 2022 installation.")

    result = run([dumpbin, "/DEPENDENTS", exe], quiet=True)
    dependencies = result.stdout or ""
    if "lynx.dll" in dependencies.lower():
        raise RuntimeError(f"Static demo unexpectedly depends on lynx.dll.\n{dependencies}")

    log("Static link check passed: lynx.dll is not a runtime dependency.")


def run_smoke_test(exe: Path, seconds: int) -> None:
    process = subprocess.Popen([str(exe)], cwd=str(exe.parent))
    try:
        try:
            exit_code = process.wait(timeout=seconds)
        except subprocess.TimeoutExpired:
            log(f"Smoke test passed: demo stayed running for {seconds} seconds.")
            return
        raise RuntimeError(f"Static demo exited during smoke test with code {exit_code}.")
    finally:
        if process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill()


def main() -> int:
    args = parse_args()
    exe = args.exe.resolve()
    if not exe.exists():
        raise RuntimeError(f"Demo executable was not built: {exe}")

    verify_static_link(exe)
    if not args.skip_smoke:
        run_smoke_test(exe, args.smoke_seconds)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(str(exc), file=sys.stderr)
        raise SystemExit(1)
