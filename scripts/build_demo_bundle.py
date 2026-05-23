from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from lynxlib_common import REPO_ROOT, log, prepend_path, remove_path, resolve_existing_path, run


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build the local Lynx demo bundle with official Lynx node tools.")
    parser.add_argument("--bundle-root", default=REPO_ROOT / "demo" / "bundle", type=Path)
    parser.add_argument("--lynx-root", default=REPO_ROOT / "third_party" / "lynx", type=Path)
    return parser.parse_args()


def find_official_node(lynx: Path) -> Path:
    candidates = [
        lynx / "buildtools" / "node" / "node.exe",
        lynx / "buildtools" / "node" / "bin" / "node",
        lynx / "buildtools" / "node" / "node",
    ]
    for candidate in candidates:
        if candidate.exists():
            return candidate
    raise RuntimeError(f"Official Node.js not found under {lynx / 'buildtools' / 'node'}. Run deps first.")


def find_official_pnpm(lynx: Path) -> Path:
    candidates = [
        lynx / "buildtools" / "node" / "pnpm.CMD",
        lynx / "buildtools" / "node" / "pnpm.cmd",
        lynx / "buildtools" / "node" / "bin" / "pnpm",
        lynx / "buildtools" / "node" / "pnpm",
    ]
    for candidate in candidates:
        if candidate.exists():
            return candidate
    raise RuntimeError(f"Official pnpm not found under {lynx / 'buildtools' / 'node'}. Run deps first.")


def main() -> int:
    args = parse_args()
    bundle = resolve_existing_path(args.bundle_root, "demo bundle root")
    lynx = resolve_existing_path(args.lynx_root, "Lynx source root")
    node = find_official_node(lynx)
    pnpm = find_official_pnpm(lynx)
    lockfile = bundle / "pnpm-lock.yaml"
    if not lockfile.exists():
        raise RuntimeError(f"Demo bundle lockfile not found: {lockfile}")

    env = os.environ.copy()
    prepend_path(env, [node.parent, node.parent / "bin"])

    legacy_node_modules = bundle / "node_modules"
    if legacy_node_modules.exists() and not (legacy_node_modules / ".modules.yaml").exists():
        log(f"Removing legacy demo node_modules: {legacy_node_modules}")
        remove_path(legacy_node_modules)

    run([pnpm, "install", "--frozen-lockfile"], cwd=bundle, env=env)
    rspeedy = bundle / "node_modules" / "@lynx-js" / "rspeedy" / "bin" / "rspeedy.js"
    if not rspeedy.exists():
        raise RuntimeError(f"Demo rspeedy not found after pnpm install: {rspeedy}")

    run([node, rspeedy, "build"], cwd=bundle, env=env)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(str(exc), file=sys.stderr)
        raise SystemExit(1)
