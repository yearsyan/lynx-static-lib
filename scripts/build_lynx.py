from __future__ import annotations

import argparse
import os
import shutil
import sys
from pathlib import Path

from lynxlib_common import REPO_ROOT, is_windows, log, prepend_path, resolve_existing_path, run


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build official Lynx Windows artifacts.")
    parser.add_argument("--target", choices=["deps", "sdk", "static", "explorer", "all"], default="all")
    parser.add_argument("--lynx-root", default=REPO_ROOT / "third_party" / "lynx", type=Path)
    parser.add_argument("--out-dir", default=REPO_ROOT / "out" / "lynx" / "Default", type=Path)
    parser.add_argument("--skip-deps", action="store_true")
    return parser.parse_args()


def find_msvc_tool(tool_name: str, env: dict[str, str]) -> Path | None:
    found = shutil.which(tool_name, path=env.get("PATH"))
    if found:
        return Path(found)

    vs_roots = []
    override = env.get("GYP_MSVS_OVERRIDE_PATH")
    if override:
        vs_roots.append(Path(override))
    for vs_base in [
        Path("C:/Program Files/Microsoft Visual Studio/2022"),
        Path("C:/Program Files (x86)/Microsoft Visual Studio/2022"),
    ]:
        vs_roots.extend(vs_base / edition for edition in ["BuildTools", "Community", "Professional", "Enterprise"])

    for root in vs_roots:
        if not root.exists():
            continue
        for candidate in root.rglob(tool_name):
            normalized = str(candidate).replace("/", "\\")
            if "\\bin\\Hostx64\\x64\\" in normalized:
                return candidate
    return None


def set_visual_studio_environment(repo_root: Path) -> dict[str, str]:
    env = os.environ.copy()
    vs_root = Path(env["GYP_MSVS_OVERRIDE_PATH"]) if env.get("GYP_MSVS_OVERRIDE_PATH") else None
    if not vs_root:
        for vs_base in [
            Path("C:/Program Files/Microsoft Visual Studio/2022"),
            Path("C:/Program Files (x86)/Microsoft Visual Studio/2022"),
        ]:
            for edition in ["BuildTools", "Community", "Professional", "Enterprise"]:
                candidate = vs_base / edition
                if candidate.exists():
                    vs_root = candidate
                    break
            if vs_root:
                break

    if not vs_root:
        raise RuntimeError("Visual Studio 2022 was not found. Install VS 2022 C++ build tools before building Lynx.")

    vcvars = vs_root / "VC" / "Auxiliary" / "Build" / "vcvarsall.bat"
    if not vcvars.exists():
        raise RuntimeError(f"vcvarsall.bat not found under Visual Studio root: {vs_root}")

    vs_clang = vs_root / "VC" / "Tools" / "Llvm" / "x64" / "bin" / "clang-cl.exe"
    vs_lld = vs_root / "VC" / "Tools" / "Llvm" / "x64" / "bin" / "lld-link.exe"
    if not vs_clang.exists() or not vs_lld.exists():
        raise RuntimeError(
            "Lynx's Windows GN toolchain requires the Visual Studio LLVM/Clang toolset.\n"
            "Install Visual Studio components:\n"
            "  Microsoft.VisualStudio.Component.VC.Llvm.Clang\n"
            "  Microsoft.VisualStudio.Component.VC.Llvm.ClangToolset\n"
            f"Expected:\n  {vs_clang}\n  {vs_lld}"
        )

    env["GYP_MSVS_OVERRIDE_PATH"] = str(vs_root)
    env["vs2022_install"] = str(vs_root)
    env.setdefault("WINDOWSSDKDIR", "C:/Program Files (x86)/Windows Kits/10")
    env["DEPOT_TOOLS_WIN_TOOLCHAIN"] = "0"
    # Static CI builds do not ship SDK debugger DLLs, and CI images may omit Windows Debugging Tools.
    env["LYNXLIB_SKIP_DEBUGGER_DLLS"] = "1"

    python = Path(sys.executable).resolve()
    shim_dir = repo_root / "third_party" / "_cache" / "python-shim"
    shim_dir.mkdir(parents=True, exist_ok=True)
    (shim_dir / "python3.cmd").write_text(f'@echo off\r\n"{python}" %*\r\n', encoding="ascii")
    if python.name.lower() == "python.exe":
        shutil.copy2(python, shim_dir / "python3.exe")
    prepend_path(env, [shim_dir, python.parent])
    return env


def get_gn_args(use_clang: bool) -> str:
    return "\n".join(
        [
            "desktop_enable_embedder_layer = true",
            "enable_clay_standalone = true",
            "disable_visibility_hidden = true",
            "use_flutter_cxx = false",
            "use_ndk_static_cxx = false",
            "enable_linker_map = false",
            "enable_clay = true",
            "is_headless = true",
            "skia_enable_flutter_defines = true",
            "skia_use_dng_sdk = false",
            "skia_use_sfntly = false",
            "skia_enable_pdf = false",
            "skia_enable_svg = true",
            "enable_svg = true",
            "skia_enable_skottie = true",
            "skia_use_x11 = false",
            "skia_use_wuffs = true",
            "skia_use_expat = true",
            "skia_use_fontconfig = false",
            "clay_enable_skshaper = true",
            "skia_use_icu = true",
            "allow_deprecated_api_calls = true",
            "stripped_symbols = true",
            "is_official_build = true",
            "enable_lto = false",
            "lynx_export_symbols = false",
            "base_export_symbols = false",
            "lynx_static_link = true",
            f"is_clang = {'true' if use_clang else 'false'}",
            "enable_lepusng_worklet = true",
            "enable_napi_binding = true",
            "is_debug = false",
            "enable_inspector = true",
            "enable_libcpp_abi_namespace_cr = false",
            'jsengine_type = "quickjs"',
            "",
        ]
    )


def invoke_gn_gen(gn: Path, out_dir: Path, source_root: Path, use_clang: bool, env: dict[str, str]) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "args.gn").write_text(get_gn_args(use_clang), encoding="ascii")
    log(f"Generating GN build: {out_dir}")
    run([gn, "gen", out_dir, "--ide=vs"], cwd=source_root, env=env)


def invoke_ninja_target(ninja: Path, out_dir: Path, ninja_target: str, env: dict[str, str]) -> None:
    log(f"Building GN target: {ninja_target}")
    run([ninja, "-C", out_dir, ninja_target], env=env)


def new_static_archive(out_dir: Path, env: dict[str, str]) -> None:
    obj_root = out_dir / "obj"
    if not obj_root.exists():
        raise RuntimeError(f"GN object directory does not exist: {obj_root}")

    objects = [
        path
        for path in obj_root.rglob("*.obj")
        if "\\obj\\explorer\\" not in str(path).replace("/", "\\")
        and "\\obj\\testing\\" not in str(path).replace("/", "\\")
    ]
    objects.sort()
    if not objects:
        raise RuntimeError(f"No object files found under {obj_root}")

    libraries: list[Path] = []
    boring_ssl_asm = obj_root / "third_party" / "boringssl" / "boringssl_asm.lib"
    if boring_ssl_asm.exists():
        libraries.append(boring_ssl_asm)

    archive = out_dir / "lynx_static.lib"
    rsp = out_dir / "lynx_static.objects.rsp"
    rsp.write_text("\n".join(f'"{path}"' for path in objects + libraries), encoding="ascii")

    lib = find_msvc_tool("lib.exe", env) or find_msvc_tool("llvm-lib.exe", env)
    if not lib:
        raise RuntimeError("Could not find lib.exe or llvm-lib.exe")

    log(f"Archiving {len(objects)} official Lynx object files and {len(libraries)} static libraries into {archive}")
    run([lib, "/NOLOGO", f"/OUT:{archive}", f"@{rsp}"], env=env)


def main() -> int:
    args = parse_args()
    repo_root = REPO_ROOT
    lynx = resolve_existing_path(args.lynx_root, "Lynx source root")
    out_dir = args.out_dir.resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    if not args.skip_deps or args.target == "deps":
        run([sys.executable, repo_root / "scripts" / "sync_lynx_deps.py", "--lynx-root", lynx])
    if args.target == "deps":
        return 0

    if not is_windows():
        raise RuntimeError("The current official Lynx static demo driver supports Windows. macOS hooks can be added here.")

    env = set_visual_studio_environment(repo_root)
    clang = Path(env["GYP_MSVS_OVERRIDE_PATH"]) / "VC" / "Tools" / "Llvm" / "x64" / "bin" / "clang-cl.exe"
    if not clang.exists():
        raise RuntimeError("Visual Studio LLVM clang-cl.exe was not found after environment setup.")
    log("Using Visual Studio LLVM clang-cl.exe toolchain.")

    py_deps = lynx / "third_party" / "py_deps"
    if py_deps.exists():
        env["PYTHONPATH"] = str(py_deps) + (os.pathsep + env["PYTHONPATH"] if env.get("PYTHONPATH") else "")

    gn = lynx / "buildtools" / "gn" / "gn.exe"
    ninja = lynx / "buildtools" / "ninja" / "ninja.exe"
    if not gn.exists():
        raise RuntimeError(f"GN not found after dependency sync: {gn}")
    if not ninja.exists():
        raise RuntimeError(f"Ninja not found after dependency sync: {ninja}")

    invoke_gn_gen(gn, out_dir, lynx, True, env)

    if args.target == "sdk":
        invoke_ninja_target(ninja, out_dir, "platform/windows:package_sdk", env)
    elif args.target == "static":
        invoke_ninja_target(ninja, out_dir, "platform/windows:windows", env)
        new_static_archive(out_dir, env)
    elif args.target == "explorer":
        invoke_ninja_target(ninja, out_dir, "explorer", env)
    elif args.target == "all":
        invoke_ninja_target(ninja, out_dir, "platform/windows:package_sdk", env)
        invoke_ninja_target(ninja, out_dir, "platform/windows:windows", env)
        new_static_archive(out_dir, env)
        invoke_ninja_target(ninja, out_dir, "explorer", env)

    log(f"Lynx Windows target '{args.target}' completed.")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(str(exc), file=sys.stderr)
        raise SystemExit(1)
