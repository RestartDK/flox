from __future__ import annotations

import os
from pathlib import Path


def repository_root() -> Path:
    override = os.getenv("FLOX_REPO_ROOT")
    if override:
        return Path(override).resolve()

    candidates: list[Path] = []
    cwd = Path.cwd().resolve()
    candidates.extend([cwd, *cwd.parents])

    file_path = Path(__file__).resolve()
    candidates.extend(file_path.parents)

    seen: set[Path] = set()
    for candidate in candidates:
        if candidate in seen:
            continue
        seen.add(candidate)
        if (candidate / "package.json").exists() and (candidate / "apps").is_dir():
            return candidate

    return cwd
