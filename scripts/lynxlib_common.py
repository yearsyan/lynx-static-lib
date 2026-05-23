from __future__ import annotations

import hashlib
import os
import shutil
import stat
import subprocess
import sys
import urllib.request
from pathlib import Path
from typing import Iterable, Sequence


REPO_ROOT = Path(__file__).resolve().parents[1]


def log(message: str) -> None:
    print(message, flush=True)


def is_windows() -> bool:
    return os.name == "nt"


def is_macos() -> bool:
    return sys.platform == "darwin"


def resolve_existing_path(path: str | Path, name: str) -> Path:
    resolved = Path(path).expanduser().resolve()
    if not resolved.exists():
        raise RuntimeError(f"{name} not found: {resolved}")
    return resolved


def run(
    args: Sequence[str | Path],
    *,
    cwd: str | Path | None = None,
    env: dict[str, str] | None = None,
    check: bool = True,
    quiet: bool = False,
) -> subprocess.CompletedProcess[str]:
    display = " ".join(str(arg) for arg in args)
    if not quiet:
        log(display)
    completed = subprocess.run(
        [str(arg) for arg in args],
        cwd=str(cwd) if cwd is not None else None,
        env=env,
        text=True,
        stdout=subprocess.PIPE if quiet else None,
        stderr=subprocess.PIPE if quiet else None,
    )
    if check and completed.returncode != 0:
        if quiet:
            if completed.stdout:
                sys.stdout.write(completed.stdout)
            if completed.stderr:
                sys.stderr.write(completed.stderr)
        raise RuntimeError(f"Command failed with exit code {completed.returncode}: {display}")
    return completed


def sha256_file(path: str | Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as file:
        for chunk in iter(lambda: file.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def download_file(url: str, destination: str | Path) -> None:
    destination = Path(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    log(f"Downloading {url}")
    with urllib.request.urlopen(url) as response, destination.open("wb") as output:
        shutil.copyfileobj(response, output)


def prepend_path(env: dict[str, str], paths: Iterable[str | Path]) -> None:
    entries = [str(Path(path)) for path in paths if path]
    if entries:
        env["PATH"] = os.pathsep.join(entries + [env.get("PATH", "")])


def copytree_replace(source: str | Path, destination: str | Path) -> None:
    destination = Path(destination)
    if destination.exists() or destination.is_symlink():
        remove_path(destination)
    shutil.copytree(source, destination)


def remove_path(path: str | Path) -> None:
    path = Path(path)
    if not path.exists() and not path.is_symlink():
        return
    if path.is_symlink():
        if path.is_dir():
            path.rmdir()
        else:
            path.unlink()
        return
    if is_windows() and is_reparse_point(path):
        path.rmdir()
        return
    if path.is_file():
        path.unlink()
        return
    shutil.rmtree(path)


def is_reparse_point(path: Path) -> bool:
    attributes = getattr(path.lstat(), "st_file_attributes", 0)
    return bool(attributes & stat.FILE_ATTRIBUTE_REPARSE_POINT)
