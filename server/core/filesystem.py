from __future__ import annotations

import shutil
from pathlib import Path

from server.config import AppConfig


def ensure_runtime_dirs(cfg: AppConfig) -> None:
    for p in (
        cfg.paths.students_dir,
        cfg.paths.temp_dir,
        cfg.paths.logs_dir,
        cfg.paths.artifacts_dir,
        cfg.paths.template_dir,
    ):
        p.mkdir(parents=True, exist_ok=True)


def copy_tree(src: Path, dst: Path) -> None:
    if dst.exists():
        shutil.rmtree(dst)
    shutil.copytree(src, dst)


def overlay_tree(src: Path, dst: Path) -> None:
    dst.mkdir(parents=True, exist_ok=True)
    for entry in src.rglob("*"):
        rel = entry.relative_to(src)
        target = dst / rel
        if entry.is_dir():
            target.mkdir(parents=True, exist_ok=True)
        else:
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(entry, target)
