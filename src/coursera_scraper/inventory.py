"""Inventory of locally downloaded courses.

Walks ``<out_dir>/<course-slug>/<MM>-<module-slug>/`` and summarizes, per
course and module, file counts by content kind plus total size. Pure disk
scan — no network, no auth.
"""

from __future__ import annotations

import re
from pathlib import Path

_MODULE_DIR_RE = re.compile(r"(\d+)-(.+)")


def classify(path: Path, module_dir: Path) -> str:
    """Classify a downloaded file by kind for the inventory summary."""
    name = path.name
    try:
        rel_parts = path.relative_to(module_dir).parts
    except ValueError:
        rel_parts = ()
    if "assets" in rel_parts:
        return "images"
    if path.suffix.lower() in {".png", ".jpg", ".jpeg", ".gif", ".webp"}:
        return "images"
    if "-transcript." in name:
        return "transcripts"
    if "-reading." in name:
        return "readings"
    if "-slides-" in name:
        return "slides"
    if path.suffix.lower() == ".mp4":
        return "videos"
    return "other"


def _empty_counts() -> dict:
    return {"videos": 0, "transcripts": 0, "readings": 0, "slides": 0, "images": 0, "other": 0}


def scan_downloads(out_dir) -> list[dict]:
    """Return one entry per downloaded course found under ``out_dir``.

    Each entry: ``{"slug", "modules": [...], "files": {...counts...}, "size"}``.
    Module entries: ``{"index", "slug", "files": {...}, "size"}``.
    """
    root = Path(out_dir)
    courses = []
    if not root.is_dir():
        return courses
    for course_dir in sorted(root.iterdir(), key=lambda p: p.name):
        if not course_dir.is_dir():
            continue
        modules = []
        for child in sorted(course_dir.iterdir(), key=lambda p: p.name):
            if not child.is_dir():
                continue
            m = _MODULE_DIR_RE.fullmatch(child.name)
            if not m:
                continue
            counts = _empty_counts()
            size = 0
            for path in child.rglob("*"):
                if not path.is_file():
                    continue
                counts[classify(path, child)] += 1
                try:
                    size += path.stat().st_size
                except OSError:
                    pass
            modules.append(
                {"index": int(m.group(1)), "slug": m.group(2), "files": counts, "size": size}
            )
        if not modules:
            continue
        totals = _empty_counts()
        for mod in modules:
            for kind, n in mod["files"].items():
                totals[kind] = totals.get(kind, 0) + n
        courses.append(
            {
                "slug": course_dir.name,
                "modules": modules,
                "files": totals,
                "size": sum(m["size"] for m in modules),
            }
        )
    return courses


def format_size(n: int) -> str:
    value = float(n)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if value < 1024 or unit == "TB":
            return f"{value:.1f} {unit}" if unit != "B" else f"{int(value)} B"
        value /= 1024
    return f"{value:.1f} TB"
