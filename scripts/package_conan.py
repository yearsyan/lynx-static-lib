from __future__ import annotations

import argparse
import os
import shutil
import sys
from pathlib import Path

from build_lynx import find_msvc_tool
from lynxlib_common import REPO_ROOT, copytree_replace, log, resolve_existing_path, run


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Package and optionally upload lynxlib static artifacts with Conan.")
    parser.add_argument("--version", default="0.1.1")
    parser.add_argument("--user", default="neuyan")
    parser.add_argument("--channel", default="stable")
    parser.add_argument("--remote", default="neuyan")
    parser.add_argument("--profile", default=REPO_ROOT / "profiles" / "windows-msvc-static", type=Path)
    parser.add_argument("--lynx-root", default=REPO_ROOT / "third_party" / "lynx", type=Path)
    parser.add_argument("--out-dir", default=REPO_ROOT / "out" / "lynx" / "Default", type=Path)
    parser.add_argument("--output-folder", default=REPO_ROOT / "build" / "conan-package", type=Path)
    parser.add_argument("--strip-debug", dest="strip_debug", action="store_true", default=True)
    parser.add_argument("--no-strip-debug", dest="strip_debug", action="store_false")
    parser.add_argument(
        "--library-only",
        action="store_true",
        help="Only export/upload the lynxlib static library package; skip lynxlib-runtime/ICU packaging.",
    )
    parser.add_argument("--skip-build", action="store_true")
    parser.add_argument("--upload", action="store_true")
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args()


def package_reference(args: argparse.Namespace) -> str:
    return f"lynxlib/{args.version}@{args.user}/{args.channel}"


def runtime_package_reference(args: argparse.Namespace) -> str:
    return f"lynxlib-runtime/{args.version}@{args.user}/{args.channel}"


def require_artifacts(out_dir: Path, include_runtime: bool) -> None:
    required = [
        out_dir / "lynx_static.lib",
        out_dir / "include",
    ]
    if include_runtime:
        required.append(out_dir / "icudtl.dat")
    missing = [path for path in required if not path.exists()]
    if missing:
        formatted = "\n  ".join(str(path) for path in missing)
        raise RuntimeError(f"Missing Lynx static package artifact(s):\n  {formatted}")


def prepare_package_artifacts(out_dir: Path, output_folder: Path, strip_debug: bool, include_runtime: bool) -> Path:
    if not strip_debug:
        return out_dir

    package_out = output_folder / "artifacts"
    package_out.mkdir(parents=True, exist_ok=True)
    copytree_replace(out_dir / "include", package_out / "include")
    if include_runtime:
        shutil.copy2(out_dir / "icudtl.dat", package_out / "icudtl.dat")
    shutil.copy2(out_dir / "lynx_static.lib", package_out / "lynx_static.lib")

    llvm_strip = find_msvc_tool("llvm-strip.exe", os.environ.copy()) or shutil.which("llvm-strip")
    if not llvm_strip:
        raise RuntimeError("llvm-strip.exe was not found; rerun with --no-strip-debug to package the raw archive.")

    log(f"Stripping debug information from package copy: {package_out / 'lynx_static.lib'}")
    run([llvm_strip, "--strip-debug", package_out / "lynx_static.lib"])
    return package_out


def main() -> int:
    args = parse_args()
    out_dir = args.out_dir.resolve()
    profile = resolve_existing_path(args.profile, "Conan profile")
    include_runtime = not args.library_only

    if not args.skip_build:
        run(
            [
                sys.executable,
                REPO_ROOT / "scripts" / "build_lynx.py",
                "--target",
                "static",
                "--lynx-root",
                args.lynx_root,
                "--out-dir",
                out_dir,
                "--skip-deps",
            ],
            cwd=REPO_ROOT,
        )

    require_artifacts(out_dir, include_runtime)
    package_out_dir = prepare_package_artifacts(out_dir, args.output_folder, args.strip_debug, include_runtime)
    require_artifacts(package_out_dir, include_runtime)

    env = os.environ.copy()
    env["LYNXLIB_PACKAGE_OUT_DIR"] = str(package_out_dir)

    refs = [
        (package_reference(args), REPO_ROOT, "lynxlib", args.output_folder / "lynxlib"),
    ]
    if include_runtime:
        refs.append(
            (runtime_package_reference(args), REPO_ROOT / "runtime", "lynxlib-runtime", args.output_folder / "runtime")
        )

    for ref, recipe_dir, name, output_folder in refs:
        log(f"Exporting Conan package: {ref}")
        run(
            [
                "conan",
                "export-pkg",
                recipe_dir,
                "-of",
                output_folder,
                "--name",
                name,
                "--version",
                args.version,
                "--user",
                args.user,
                "--channel",
                args.channel,
                "-pr:a",
                profile,
            ],
            cwd=REPO_ROOT,
            env=env,
        )

    if args.upload:
        for ref, _, _, _ in refs:
            upload_args = ["conan", "upload", f"{ref}:*", "-r", args.remote, "-c"]
            if args.force:
                upload_args.append("--force")
            if args.dry_run:
                upload_args.append("--dry-run")
            log(f"Uploading Conan package to remote '{args.remote}': {ref}")
            run(upload_args, cwd=REPO_ROOT)

    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(str(exc), file=sys.stderr)
        raise SystemExit(1)
