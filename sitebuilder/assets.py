"""Copy static assets and compute cache-busting versions."""
from __future__ import annotations

import hashlib
import shutil
from pathlib import Path


def copy_static(static_dir: Path, out_dir: Path) -> dict[str, str]:
    """Copy ``web/static/*`` into the site root. Returns {filename: hash8}."""
    versions: dict[str, str] = {}
    for src in sorted(static_dir.rglob("*")):
        if src.is_dir():
            continue
        rel = src.relative_to(static_dir)
        dst = out_dir / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(src, dst)
        versions[str(rel).replace("\\", "/")] = hashlib.sha256(src.read_bytes()).hexdigest()[:8]
    (out_dir / ".nojekyll").write_text("", encoding="utf-8")
    return versions
