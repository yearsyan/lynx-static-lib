from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from lynxlib_common import REPO_ROOT, log, resolve_existing_path, run


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build and package lynxlib-http with Conan.")
    parser.add_argument("--version", default="0.2")
    parser.add_argument("--user", default="neuyan")
    parser.add_argument("--channel", default="stable")
    parser.add_argument("--remote", default="neuyan")
    parser.add_argument("--dependency-remote", default="conancenter")
    parser.add_argument("--profile", default=REPO_ROOT / "profiles" / "windows-msvc-static", type=Path)
    parser.add_argument("--lynxlib-ref")
    parser.add_argument("--libcurl-ref", default="libcurl/8.20.0")
    parser.add_argument("--upload", action="store_true")
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args()


def package_reference(args: argparse.Namespace) -> str:
    return f"lynxlib-http/{args.version}@{args.user}/{args.channel}"


def main() -> int:
    args = parse_args()
    profile = resolve_existing_path(args.profile, "Conan profile")
    lynxlib_ref = args.lynxlib_ref or f"lynxlib/{args.version}@{args.user}/{args.channel}"

    env = os.environ.copy()
    env["LYNXLIB_HTTP_LYNXLIB_REF"] = lynxlib_ref
    env["LYNXLIB_HTTP_LIBCURL_REF"] = args.libcurl_ref

    ref = package_reference(args)
    log(f"Creating Conan package: {ref}")
    log(f"Using Lynx package: {lynxlib_ref}")
    log(f"Using curl package: {args.libcurl_ref}")
    create_args = [
        "conan",
        "create",
        REPO_ROOT / "http",
        "--name",
        "lynxlib-http",
        "--version",
        args.version,
        "--user",
        args.user,
        "--channel",
        args.channel,
        "-pr:a",
        profile,
        "--build=missing",
    ]
    if args.dependency_remote:
        create_args.extend(["-r", args.dependency_remote])

    run(
        create_args,
        cwd=REPO_ROOT,
        env=env,
    )

    if args.upload:
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
