from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path

from invoke_cmake import find_cmake
from lynxlib_common import REPO_ROOT, log, prepend_path, resolve_existing_path, run


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Install Conan deps and build the standalone Lynx static demo.")
    parser.add_argument("--demo-root", default=REPO_ROOT / "demo", type=Path)
    parser.add_argument("--profile", default=REPO_ROOT / "demo" / "profiles" / "windows-msvc-static", type=Path)
    parser.add_argument("--remote", default="neuyan")
    parser.add_argument("--build-type", default="Release")
    parser.add_argument("--configure-only", action="store_true")
    return parser.parse_args()


def ensure_ninja_on_path(env: dict[str, str]) -> None:
    if shutil.which("ninja", path=env.get("PATH")):
        return

    vs_root = Path(env["GYP_MSVS_OVERRIDE_PATH"])
    candidate = vs_root / "Common7" / "IDE" / "CommonExtensions" / "Microsoft" / "CMake" / "Ninja"
    if (candidate / "ninja.exe").exists():
        prepend_path(env, [candidate])


def find_visual_studio_root(env: dict[str, str]) -> Path:
    override = env.get("GYP_MSVS_OVERRIDE_PATH")
    if override:
        candidate = Path(override)
        if (candidate / "VC" / "Auxiliary" / "Build" / "vcvarsall.bat").exists():
            return candidate

    for vs_base in [
        Path("C:/Program Files/Microsoft Visual Studio/2022"),
        Path("C:/Program Files (x86)/Microsoft Visual Studio/2022"),
    ]:
        for edition in ["BuildTools", "Community", "Professional", "Enterprise"]:
            candidate = vs_base / edition
            if (candidate / "VC" / "Auxiliary" / "Build" / "vcvarsall.bat").exists():
                return candidate

    raise RuntimeError("Visual Studio 2022 C++ build tools were not found.")


def load_vcvars_environment(env: dict[str, str]) -> None:
    vs_root = find_visual_studio_root(env)
    env["GYP_MSVS_OVERRIDE_PATH"] = str(vs_root)
    vcvars = vs_root / "VC" / "Auxiliary" / "Build" / "vcvarsall.bat"

    command = f'cmd.exe /d /c call "{vcvars}" x64 ^>nul ^&^& set'
    completed = subprocess.run(
        command,
        env=env,
        shell=True,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    if completed.returncode != 0:
        if completed.stdout:
            sys.stdout.write(completed.stdout)
        if completed.stderr:
            sys.stderr.write(completed.stderr)
        raise RuntimeError(f"Command failed with exit code {completed.returncode}: {command}")
    for line in completed.stdout.splitlines():
        if "=" not in line:
            continue
        key, value = line.split("=", 1)
        env[key] = value


def main() -> int:
    args = parse_args()
    demo_root = resolve_existing_path(args.demo_root, "demo root")
    profile = resolve_existing_path(args.profile, "Conan profile")
    build_dir = demo_root / "build" / args.build_type
    toolchain = build_dir / "generators" / "conan_toolchain.cmake"

    env = os.environ.copy()
    load_vcvars_environment(env)
    ensure_ninja_on_path(env)

    run(
        [
            "conan",
            "install",
            demo_root,
            "-pr:a",
            profile,
            "-s:a",
            f"build_type={args.build_type}",
            "-r",
            args.remote,
            "--build=missing",
        ],
        cwd=demo_root,
        env=env,
    )
    if not toolchain.exists():
        raise RuntimeError(f"Conan toolchain file was not generated: {toolchain}")

    cmake = find_cmake()
    run(
        [
            cmake,
            "-S",
            demo_root,
            "-B",
            build_dir,
            "-G",
            "Ninja",
            f"-DCMAKE_BUILD_TYPE={args.build_type}",
            "-DCMAKE_EXPORT_COMPILE_COMMANDS=ON",
            f"-DCMAKE_TOOLCHAIN_FILE={toolchain}",
        ],
        cwd=demo_root,
        env=env,
    )

    if not args.configure_only:
        run([cmake, "--build", build_dir], cwd=demo_root, env=env)

    compile_commands = build_dir / "compile_commands.json"
    if compile_commands.exists():
        log(f"compile_commands.json: {compile_commands}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(str(exc), file=sys.stderr)
        raise SystemExit(1)
