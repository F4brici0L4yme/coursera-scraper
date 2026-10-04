"""Upload downloaded course material to Gemini Notebook via the ``nlm`` CLI.

Design: shell out to ``nlm`` (from ``notebooklm-mcp-cli``) instead of
reimplementing NotebookLM's internal API. One notebook per module, since
NotebookLM caps the number of sources per notebook.

Uploadable files (already on disk under ``downloads/<slug>/``):
  ``*-transcript.txt``, ``*-reading.txt`` (not the ``.html`` twin),
  ``*-slides-*.pdf`` (or ``.ipynb``), lecture-attached ``*.ipynb``.
Skipped: ``.mp4`` (transcripts carry the spoken content), reading images,
``.html`` duplicates, ``.generic`` leftovers.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
from pathlib import Path

NLM_BIN = "nlm"

INSTALL_HINT = (
    "The 'nlm' CLI was not found on PATH. Install it with: uv tool install notebooklm-mcp-cli"
)

UPLOADABLE_SUFFIXES = {".txt", ".pdf", ".ipynb"}

_MODULE_DIR_RE = re.compile(r"(\d+)-(.+)")
_STEM_RES = [
    (re.compile(r"(\d+)-(.+)-transcript"), "transcript"),
    (re.compile(r"(\d+)-(.+)-reading"), "reading"),
    (re.compile(r"(\d+)-(.+)-slides(?:-(\d+))?"), "slides"),
]


class NotebookError(Exception):
    """Failure talking to the ``nlm`` CLI."""


def _pretty(text: str) -> str:
    return text.replace("-", " ").replace("_", " ").strip()


def _title_for(stem: str, module_idx: int, module_name: str) -> str:
    for rx, kind in _STEM_RES:
        m = rx.fullmatch(stem)
        if not m:
            continue
        nn, item = m.group(1), _pretty(m.group(2))
        label = kind
        if kind == "slides" and m.lastindex == 3 and m.group(3):
            label = f"slides {m.group(3)}"
        return f"{module_idx:02d} {_pretty(module_name)} / {nn} {item} ({label})"
    return f"{module_idx:02d} {_pretty(module_name)} / {_pretty(stem)}"


def _module_dirs(course_dir: Path, module_filter) -> list[tuple[int, str, Path]]:
    entries = []
    for child in sorted(course_dir.iterdir()):
        if not child.is_dir():
            continue
        m = _MODULE_DIR_RE.fullmatch(child.name)
        if m:
            entries.append((int(m.group(1)), m.group(2), child))
    if module_filter is None:
        return entries
    filters = module_filter if isinstance(module_filter, list) else [module_filter]
    selected = [
        (i, slug, path)
        for i, slug, path in entries
        if any(
            (isinstance(f, int) and f == i) or (isinstance(f, str) and f == slug) for f in filters
        )
    ]
    if not selected:
        available = ", ".join(f"{i}:{s}" for i, s, _ in entries)
        raise NotebookError(f"Module {module_filter!r} not found. Available modules: {available}.")
    return selected


def _candidates(module_dir: Path, module_idx: int, module_slug: str):
    for path in sorted(module_dir.rglob("*")):
        if not path.is_file() or "assets" in path.relative_to(module_dir).parts:
            continue
        if path.suffix.lower() not in UPLOADABLE_SUFFIXES:
            continue
        yield path, _title_for(path.stem, module_idx, module_slug)


def run_nlm(*args: str, profile: str | None = None):
    """Run ``nlm`` with ``--json`` and return the parsed JSON payload."""
    exe = shutil.which(NLM_BIN)
    if not exe:
        raise NotebookError(INSTALL_HINT)
    cmd = [exe, *args, "--json"]
    if profile:
        cmd += ["--profile", profile]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=1800)
    except subprocess.TimeoutExpired as exc:
        raise NotebookError(f"nlm timed out: {' '.join(cmd[:4])}...") from exc
    if proc.returncode != 0:
        err = (proc.stderr or proc.stdout or "").strip()[-500:]
        raise NotebookError(f"nlm failed ({' '.join(cmd[1:4])}...): {err}")
    try:
        return json.loads(proc.stdout)
    except json.JSONDecodeError as exc:
        raise NotebookError(f"Could not parse nlm JSON output: {proc.stdout[:200]}") from exc


def _as_list(data) -> list:
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        for key in ("items", "notebooks", "sources", "results", "data"):
            if isinstance(data.get(key), list):
                return data[key]
    raise NotebookError(f"Unexpected JSON from nlm: {str(data)[:200]}")


def _pick(item: dict, *keys: str, default=None):
    for key in keys:
        if item.get(key) is not None:
            return item[key]
    return default


def ensure_notebook(name: str, profile: str | None = None) -> tuple[str, bool]:
    """Return ``(notebook_id, created)`` for a notebook with this exact title."""
    for nb in _as_list(run_nlm("notebook", "list", profile=profile)):
        if not isinstance(nb, dict):
            continue
        if _pick(nb, "title", "name") == name:
            nb_id = _pick(nb, "id", "notebook_id")
            if nb_id:
                return str(nb_id), False
    created = run_nlm("notebook", "create", name, profile=profile)
    if isinstance(created, dict):
        nb_id = _pick(created, "notebook_id", "id")
        if nb_id:
            return str(nb_id), True
    raise NotebookError(f"Could not determine id of created notebook {name!r}.")


def existing_titles(notebook_id: str, profile: str | None = None) -> set[str]:
    """Return the set of source titles already in the notebook."""
    titles = set()
    for src in _as_list(run_nlm("source", "list", notebook_id, profile=profile)):
        if isinstance(src, dict):
            title = _pick(src, "title", "name")
            if title:
                titles.add(str(title))
    return titles


def upload_course(
    out_dir,
    slug: str,
    module_filter=None,
    notebook: str | None = None,
    dry_run: bool = False,
    force: bool = False,
    wait: bool = True,
    profile: str | None = None,
    progress=None,
) -> dict:
    """Upload a downloaded course (or modules) to Gemini Notebook(s).

    Default: one notebook per module named ``"<slug> — M<MM> <module>"``;
    ``notebook`` overrides with a single target notebook for everything.
    """
    course_dir = Path(out_dir) / slug
    if not course_dir.is_dir():
        raise NotebookError(
            f"No downloads found for '{slug}' in {course_dir}. Run 'download' first."
        )
    modules = _module_dirs(course_dir, module_filter)

    results = {"notebooks": [], "ok": 0, "skip": 0, "failed": 0}
    if dry_run:
        if shutil.which(NLM_BIN) is None:
            print(f"(note: {INSTALL_HINT})")
        for idx, mslug, mdir in modules:
            nb_name = notebook or f"{slug} — M{idx:02d} {_pretty(mslug)}"
            cands = list(_candidates(mdir, idx, mslug))
            print(f"[dry-run] notebook {nb_name!r}: {len(cands)} file(s)")
            for path, title in cands:
                print(f"  would upload: {title}  <-  {path.name}")
                results["ok"] += 1
        return results

    total = sum(1 for _, _, mdir in modules for _ in _candidates(mdir, 0, ""))
    if progress:
        progress({"type": "start", "total": total})

    for idx, mslug, mdir in modules:
        nb_name = notebook or f"{slug} — M{idx:02d} {_pretty(mslug)}"
        nb_id, created = ensure_notebook(nb_name, profile)
        results["notebooks"].append({"name": nb_name, "created": created})
        known = set() if force else existing_titles(nb_id, profile)
        for path, title in _candidates(mdir, idx, mslug):
            if title in known and not force:
                results["skip"] += 1
                if progress:
                    progress({"type": "file", "dest": title, "status": "skip", "error": None})
                continue
            try:
                cmd = ["source", "add", nb_id, "--file", str(path.resolve()), "--title", title]
                if wait:
                    cmd.append("--wait")
                run_nlm(*cmd, profile=profile)
                results["ok"] += 1
                status, error = "ok", None
            except NotebookError as exc:
                results["failed"] += 1
                status, error = "failed", str(exc)
            if progress:
                progress({"type": "file", "dest": title, "status": status, "error": error})
    return results
