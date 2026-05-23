from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
from pathlib import Path

from lynxlib_common import (
    REPO_ROOT,
    copytree_replace,
    download_file,
    is_macos,
    is_windows,
    log,
    prepend_path,
    resolve_existing_path,
    run,
    sha256_file,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Synchronize pinned official Lynx dependencies.")
    parser.add_argument(
        "--lynx-root",
        default=REPO_ROOT / "third_party" / "lynx",
        type=Path,
        help="Path to the official Lynx source tree.",
    )
    return parser.parse_args()


def load_manifest() -> dict:
    manifest_path = REPO_ROOT / "third_party" / "official_deps.manifest.json"
    with manifest_path.open("r", encoding="utf-8") as file:
        return json.load(file)


def apply_git_patches(repo_path: Path, patch_dir: Path, label: str) -> None:
    if not patch_dir.exists():
        return

    for patch in sorted(patch_dir.glob("*.patch")):
        log(f"Applying local {label} compatibility patch: {patch.name}")
        check = run(["git", "-C", repo_path, "apply", "--check", patch], check=False, quiet=True)
        if check.returncode == 0:
            run(["git", "-C", repo_path, "apply", patch])
            continue

        reverse_check = run(
            ["git", "-C", repo_path, "apply", "--reverse", "--check", patch],
            check=False,
            quiet=True,
        )
        if reverse_check.returncode == 0:
            log(f"Patch already applied: {patch.name}")
            continue

        apply_patch_by_file(repo_path, patch)


def patch_paths(patch: Path) -> list[str]:
    paths: list[str] = []
    with patch.open("r", encoding="utf-8") as file:
        for line in file:
            if not line.startswith("diff --git "):
                continue
            parts = line.strip().split()
            if len(parts) < 4 or not parts[3].startswith("b/"):
                continue
            paths.append(parts[3][2:])
    return paths


def apply_patch_by_file(repo_path: Path, patch: Path) -> None:
    applied_any = False
    for path in patch_paths(patch):
        include = f"--include={path}"
        check = run(["git", "-C", repo_path, "apply", "--check", include, patch], check=False, quiet=True)
        if check.returncode == 0:
            log(f"Applying remaining patch file: {path}")
            run(["git", "-C", repo_path, "apply", include, patch])
            applied_any = True
            continue

        reverse_check = run(
            ["git", "-C", repo_path, "apply", "--reverse", "--check", include, patch],
            check=False,
            quiet=True,
        )
        if reverse_check.returncode == 0:
            log(f"Patch file already applied: {path}")
            continue

        raise RuntimeError(f"Patch file cannot be applied cleanly: {patch} ({path})")

    if not applied_any:
        log(f"Patch already applied file-by-file: {patch.name}")


def normalize_official_patch_line_endings(lynx: Path) -> None:
    patch_root = lynx / "patches"
    if not patch_root.exists():
        return

    normalized_count = 0
    for patch in patch_root.rglob("*.patch"):
        content = patch.read_bytes()
        normalized = content.replace(b"\r\n", b"\n")
        if normalized == content:
            continue
        patch.write_bytes(normalized)
        normalized_count += 1

    if normalized_count:
        log(f"Normalized line endings for {normalized_count} official Lynx patch file(s).")


def resolve_habitat(manifest: dict, cache_dir: Path) -> Path:
    habitat = manifest["habitat"]
    version = habitat["version"]

    if is_windows():
        url = habitat["windows_url"]
        expected_hash = habitat["windows_sha256"]
        executable = cache_dir / f"hab-{version}.exe"
        if not executable.exists():
            download_file(url, executable)
        actual_hash = sha256_file(executable)
        if actual_hash != expected_hash:
            raise RuntimeError(f"Habitat checksum mismatch. Expected {expected_hash}, got {actual_hash}")
        return executable

    platform_key = "macos" if is_macos() else "linux"
    url_key = f"{platform_key}_url"
    sha_key = f"{platform_key}_sha256"
    if url_key in habitat and sha_key in habitat:
        executable = cache_dir / f"hab-{version}-{platform_key}"
        if not executable.exists():
            download_file(habitat[url_key], executable)
            executable.chmod(0o755)
        actual_hash = sha256_file(executable)
        if actual_hash != habitat[sha_key]:
            raise RuntimeError(f"Habitat checksum mismatch. Expected {habitat[sha_key]}, got {actual_hash}")
        return executable

    system_hab = shutil.which("hab")
    if system_hab:
        log(f"Using Habitat from PATH: {system_hab}")
        return Path(system_hab)

    raise RuntimeError(
        f"No pinned Habitat binary is declared for {platform_key}. "
        "Add the URL and SHA-256 to third_party/official_deps.manifest.json."
    )


def find_official_tool(lynx: Path, tool_name: str) -> Path | None:
    candidates: list[Path]
    if is_windows():
        candidates = [
            lynx / "buildtools" / "node" / f"{tool_name}.CMD",
            lynx / "buildtools" / "node" / f"{tool_name}.cmd",
            lynx / "buildtools" / "node" / f"{tool_name}.exe",
        ]
    else:
        candidates = [
            lynx / "buildtools" / "node" / "bin" / tool_name,
            lynx / "buildtools" / "node" / tool_name,
        ]

    for candidate in candidates:
        if candidate.exists():
            return candidate
    return None


def install_node_workspace(manifest: dict, lynx: Path, cache_dir: Path) -> None:
    node_manifest = manifest.get("node")
    if not node_manifest:
        return

    package_manager = str(node_manifest["package_manager"])
    workspace = str(node_manifest["weak_node_api_workspace"])
    node_dir = lynx / "buildtools" / "node"
    pnpm = find_official_tool(lynx, "pnpm")
    if not pnpm:
        raise RuntimeError(f"Official Lynx pnpm was not found after dependency sync under: {node_dir}")

    env = os.environ.copy()
    prepend_path(env, [node_dir, node_dir / "bin"])

    lock_file = lynx / "pnpm-lock.yaml"
    lock_hash = sha256_file(lock_file)
    full_install_stamp = cache_dir / f"pnpm-full-workspace-{lock_hash}.stamp"
    explorer_dependency = (
        lynx
        / "devtool"
        / "base_devtool"
        / "js_libraries"
        / "logbox"
        / "node_modules"
        / "source-map"
        / "lib"
        / "mappings.wasm"
    )
    if not full_install_stamp.exists() or not explorer_dependency.exists():
        log(f"Installing full Lynx pnpm workspace with {package_manager}...")
        run([pnpm, "install", "--frozen-lockfile"], cwd=lynx, env=env)
        full_install_stamp.write_text(lock_hash, encoding="ascii")
    else:
        log(f"Full Lynx pnpm workspace is already installed for lock hash {lock_hash}.")

    expected_package = lynx / "third_party" / "weak-node-api" / "node_modules" / "@lynx-js" / "weak-node-api"
    hoisted_package = lynx / "node_modules" / "@lynx-js" / "weak-node-api"

    if not expected_package.exists():
        log(f"Installing Lynx node workspace dependency '{workspace}' with {package_manager}...")
        run([pnpm, "install", "--filter", workspace, "--frozen-lockfile"], cwd=lynx, env=env)

    if not expected_package.exists():
        if not hoisted_package.exists():
            raise RuntimeError(f"weak-node-api package was not installed at '{expected_package}' or '{hoisted_package}'")
        expected_package.parent.mkdir(parents=True, exist_ok=True)
        log("Copying hoisted weak-node-api package to the official GN script location...")
        copytree_replace(hoisted_package, expected_package)


def add_git_config(env: dict[str, str], key: str, value: str) -> None:
    index = int(env.get("GIT_CONFIG_COUNT", "0"))
    env["GIT_CONFIG_COUNT"] = str(index + 1)
    env[f"GIT_CONFIG_KEY_{index}"] = key
    env[f"GIT_CONFIG_VALUE_{index}"] = value


def dependency_sync_env(manifest: dict) -> dict[str, str]:
    env = os.environ.copy()
    env.setdefault("GIT_TERMINAL_PROMPT", "0")
    env.setdefault("GCM_INTERACTIVE", "Never")
    env.setdefault("GIT_HTTP_LOW_SPEED_LIMIT", "1024")
    env.setdefault("GIT_HTTP_LOW_SPEED_TIME", "120")

    for rewrite in manifest.get("git_url_rewrites", []):
        source = rewrite["from"]
        destination = rewrite["to"]
        log(f"Rewriting Git dependency URL for CI: {source} -> {destination}")
        add_git_config(env, f"url.{destination}.insteadOf", source)
    return env


def main() -> int:
    args = parse_args()
    manifest = load_manifest()
    lynx = resolve_existing_path(args.lynx_root, "Lynx source root")

    actual_commit = run(["git", "-C", lynx, "rev-parse", "HEAD"], quiet=True).stdout.strip()
    expected_commit = manifest["lynx"]["commit"]
    if actual_commit != expected_commit:
        raise RuntimeError(f"Lynx submodule commit mismatch. Expected {expected_commit}, got {actual_commit}")

    normalize_official_patch_line_endings(lynx)

    cache_dir = REPO_ROOT / "third_party" / "_cache"
    cache_dir.mkdir(parents=True, exist_ok=True)

    hab = resolve_habitat(manifest, cache_dir)
    log(f"Using Habitat {manifest['habitat']['version']}: {hab}")
    sync_env = dependency_sync_env(manifest)

    for target in manifest["sync_targets"]:
        if target == "default":
            log("Synchronizing Lynx default dependencies...")
            run([hab, "sync", lynx], env=sync_env)
        else:
            log(f"Synchronizing Lynx dependency target '{target}'...")
            run([hab, "sync", lynx, "--target", target], env=sync_env)

    install_node_workspace(manifest, lynx, cache_dir)
    apply_git_patches(lynx, REPO_ROOT / "patches" / "lynx", "Lynx")
    apply_git_patches(lynx / "third_party" / "quickjs" / "src", REPO_ROOT / "patches" / "quickjs-src", "QuickJS")

    log("Pinned official Lynx dependencies are ready.")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(str(exc), file=sys.stderr)
        raise SystemExit(1)
