from __future__ import annotations

import re
import sys
from pathlib import Path

from lynxlib_common import REPO_ROOT, log, run


FORBIDDEN_PREFIXES = (
    "build",
    "out",
    "third_party/_cache",
    "demo/bundle/node_modules",
    "demo/bundle/dist",
    "demo/bundle/.rspeedy",
)
FORBIDDEN_BINARY = re.compile(r"\.(exe|dll|lib|obj|pdb|zip|dat|bundle)$", re.IGNORECASE)


def is_forbidden(path: str) -> bool:
    normalized = path.replace("\\", "/")
    for prefix in FORBIDDEN_PREFIXES:
        if normalized == prefix or normalized.startswith(prefix + "/"):
            return True
    return bool(FORBIDDEN_BINARY.search(normalized))


def main() -> int:
    tracked = run(["git", "-C", REPO_ROOT, "ls-files"], quiet=True).stdout.splitlines()
    bad = [path for path in tracked if is_forbidden(path)]
    if bad:
        print("Forbidden generated or binary files are tracked:", file=sys.stderr)
        for path in bad:
            print(f"  {path}", file=sys.stderr)
        return 1
    log("OK: tracked files exclude build artifacts and binary outputs")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
