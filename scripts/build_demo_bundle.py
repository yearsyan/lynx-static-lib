from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path

from lynxlib_common import REPO_ROOT, is_windows, log, remove_path, resolve_existing_path, run


PACKAGES = [
    ("@lynx-js", "react"),
    ("@lynx-js", "react-rsbuild-plugin"),
    ("@lynx-js", "rspeedy"),
    ("@rsbuild", "plugin-sass"),
    ("typescript",),
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build the local Lynx demo bundle with official Lynx node tools.")
    parser.add_argument("--bundle-root", default=REPO_ROOT / "demo" / "bundle", type=Path)
    parser.add_argument("--lynx-root", default=REPO_ROOT / "third_party" / "lynx", type=Path)
    return parser.parse_args()


def package_path(root: Path, package: tuple[str, ...]) -> Path:
    current = root
    for part in package:
        current = current / part
    return current


def create_directory_link(link: Path, target: Path) -> None:
    remove_path(link)
    link.parent.mkdir(parents=True, exist_ok=True)
    if is_windows():
        completed = subprocess.run(
            ["cmd", "/c", "mklink", "/J", str(link), str(target)],
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
        )
        if completed.returncode != 0:
            raise RuntimeError(f"Failed to create junction {link} -> {target}:\n{completed.stdout}")
        return
    os.symlink(target, link, target_is_directory=True)


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


def main() -> int:
    args = parse_args()
    bundle = resolve_existing_path(args.bundle_root, "demo bundle root")
    lynx = resolve_existing_path(args.lynx_root, "Lynx source root")
    official_node_modules = lynx / "node_modules"
    node = find_official_node(lynx)
    rspeedy = official_node_modules / "@lynx-js" / "rspeedy" / "bin" / "rspeedy.js"

    if not rspeedy.exists():
        raise RuntimeError(f"Official rspeedy not found: {rspeedy}. Run deps first.")

    node_modules = bundle / "node_modules"
    node_modules.mkdir(parents=True, exist_ok=True)
    for package in PACKAGES:
        link = package_path(node_modules, package)
        target = package_path(official_node_modules, package)
        if not target.exists():
            raise RuntimeError(f"Official node package not found: {target}. Run deps first.")
        log(f"Linking {link} -> {target}")
        create_directory_link(link, target)

    run([node, rspeedy, "build"], cwd=bundle)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(str(exc), file=sys.stderr)
        raise SystemExit(1)
