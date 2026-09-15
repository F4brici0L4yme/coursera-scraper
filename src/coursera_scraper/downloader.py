"""Resolve download URLs and write files to disk.

Output layout (consistent and readable, per OBJECTIVE.md):

    downloads/<course-slug>/<MM>-<module-slug>/<LL>-<lesson-slug>/
        video.mp4                 (single-video lesson)
        transcript.txt            (subtitles/transcript in plain-text)

Lessons with more than one video use numbered filenames instead:
        video-<VV>-<video-slug>.mp4
        transcript-<VV>-<video-slug>.txt
"""

from __future__ import annotations

import re
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Optional

import requests

from .api import BASE, CourseraClient, CourseraError

RESOLUTION_ORDER = ["1080p", "720p", "540p", "360p", "240p"]

_SAFE_RE = re.compile(r"[^A-Za-z0-9._-]+")


def sanitize(name: str) -> str:
    return _SAFE_RE.sub("-", name).strip("-")


def pick_video_url(sources: dict, resolution: str) -> tuple[Optional[str], Optional[str]]:
    """Return (chosen_resolution, mp4/webm url) for the requested resolution."""
    by_res = sources.get("byResolution") or {}
    candidates = RESOLUTION_ORDER if resolution == "best" else [resolution] + RESOLUTION_ORDER
    for res in candidates:
        entry = by_res.get(res)
        if not entry:
            continue
        url = entry.get("mp4VideoUrl") or entry.get("webMVideoUrl")
        if url:
            return res, url
    return None, None


def _abs_url(url: str) -> str:
    return url if url.startswith("http") else BASE + url


def _pick_localized(tracks: dict, lang: str) -> tuple[Optional[str], Optional[str]]:
    """Return (actual_lang, url) preferring the requested language."""
    if lang in tracks:
        return lang, tracks[lang]
    if tracks:
        first = next(iter(tracks.items()))
        return first[0], first[1]
    return None, None


def _download_with_ytdlp(url: str, dest: Path) -> None:
    """Fallback for courses that only expose HLS/DASH playlists."""
    try:
        import yt_dlp
    except ImportError as exc:  # pragma: no cover
        raise CourseraError(
            "Course only serves HLS/DASH streams; install yt-dlp: pip install yt-dlp"
        ) from exc

    tmp_dir = dest.parent / ".ytdlp-tmp"
    tmp_dir.mkdir(parents=True, exist_ok=True)
    opts = {
        "outtmpl": str(tmp_dir / "%(id)s.%(ext)s"),
        "quiet": True,
        "noprogress": True,
        "noplaylist": True,
    }
    with yt_dlp.YoutubeDL(opts) as ydl:
        info = ydl.extract_info(url, download=True)
        downloaded = ydl.prepare_filename(info)
    Path(downloaded).replace(dest)
    for leftover in tmp_dir.iterdir():
        leftover.unlink(missing_ok=True)
    tmp_dir.rmdir()


def _download_file(kind: str, url: str, dest: Path, cauth: Optional[str], retries: int = 3) -> str:
    """Download a single file; return 'ok' or 'skip'. Raises on final failure."""
    if dest.exists() and dest.stat().st_size > 0:
        return "skip"
    dest.parent.mkdir(parents=True, exist_ok=True)
    if kind == "hls":
        _download_with_ytdlp(url, dest)
        return "ok"

    cookies = {"CAUTH": cauth} if cauth else None
    tmp = dest.with_name(dest.name + ".part")
    last_err: Optional[Exception] = None
    for attempt in range(retries):
        try:
            with requests.get(url, stream=True, timeout=60, cookies=cookies) as resp:
                resp.raise_for_status()
                with open(tmp, "wb") as f:
                    for chunk in resp.iter_content(chunk_size=1 << 16):
                        f.write(chunk)
            tmp.replace(dest)
            return "ok"
        except Exception as exc:  # noqa: BLE001 - retried with backoff
            last_err = exc
            tmp.unlink(missing_ok=True)
            time.sleep(2 ** attempt)
    raise CourseraError(f"Download failed after {retries} attempts: {last_err}") from last_err


def _resolve_lesson_tasks(client, course, module, lesson, opts) -> tuple[list, dict[str, int], int]:
    """Build (kind, url, dest) tasks for every lecture item in a lesson."""
    lang = opts["lang"]
    resolution = opts["resolution"]
    tasks: list[tuple[str, str, Path]] = []
    skipped_types: dict[str, int] = {}
    locked = 0

    lecture_items = []
    for item_id in lesson.item_ids:
        item = course.items.get(item_id)
        if item is None:
            continue
        if item.type_name == "lecture":
            lecture_items.append(item)
        else:
            skipped_types[item.type_name or "unknown"] = skipped_types.get(item.type_name or "unknown", 0) + 1

    base = (
        opts["out_dir"]
        / sanitize(course.slug)
        / f"{opts['module_idx']:02d}-{sanitize(module.slug) or module.id}"
        / f"{opts['lesson_idx']:02d}-{sanitize(lesson.slug) or lesson.id}"
    )

    multi = len(lecture_items) > 1
    for vi, item in enumerate(lecture_items, start=1):
        if item.is_locked:
            locked += 1
            continue
        vinfo = client.get_lecture_video(course.id, item.id)
        if not vinfo:
            continue
        sources = vinfo.get("sources") or {}
        playlists = sources.get("playlists") or {}

        stem = f"{vi:02d}-{sanitize(item.slug) or item.id}" if multi else ""

        if opts["include_video"]:
            _, url = pick_video_url(sources, resolution)
            video_name = f"{stem}-video.mp4" if stem else "video.mp4"
            if url:
                tasks.append(("video", url, base / video_name))
            elif playlists:
                tasks.append(("hls", playlists.get("mpeg-dash") or playlists.get("hls"), base / video_name))

        if opts["include_transcript"]:
            _, url = _pick_localized(vinfo.get("subtitlesTxt") or {}, lang)
            if url:
                tr_name = f"{stem}-transcript.txt" if stem else "transcript.txt"
                tasks.append(("text", _abs_url(url), base / tr_name))

    return tasks, skipped_types, locked


def download_course(client: CourseraClient, slug: str, **opts) -> dict:
    """Download a whole course (or a single module via opts['module_filter'])."""
    course = client.get_course(slug)

    module_filter = opts.get("module_filter")
    selected = []
    for mi, module in enumerate(course.modules, start=1):
        if module_filter is None:
            selected.append((mi, module))
        elif isinstance(module_filter, int):
            if module_filter == mi:
                selected.append((mi, module))
        elif module.slug == module_filter or module.name == module_filter:
            selected.append((mi, module))

    if not selected:
        if isinstance(module_filter, int):
            raise CourseraError(f"Module index out of range (1..{len(course.modules)}).")
        raise CourseraError(f"Module '{module_filter}' not found.")

    all_tasks: list[tuple[str, str, Path]] = []
    skipped_types: dict[str, int] = {}
    locked = 0

    for mi, module in selected:
        for li, lesson in enumerate(module.lessons, start=1):
            opt = dict(opts)
            opt["module_idx"] = mi
            opt["lesson_idx"] = li
            tasks, skipped, lk = _resolve_lesson_tasks(client, course, module, lesson, opt)
            all_tasks.extend(tasks)
            locked += lk
            for k, v in skipped.items():
                skipped_types[k] = skipped_types.get(k, 0) + v

    results = {"ok": 0, "skip": 0, "failed": 0, "tasks": len(all_tasks), "locked": locked, "skipped_types": skipped_types}
    if not all_tasks:
        return results

    cauth = opts["cauth"]
    concurrency = opts.get("concurrency", 3)
    with ThreadPoolExecutor(max_workers=concurrency) as pool:
        futures = {
            pool.submit(_download_file, kind, url, dest, cauth): (kind, dest)
            for kind, url, dest in all_tasks
        }
        for fut in as_completed(futures):
            kind, dest = futures[fut]
            try:
                status = fut.result()
            except Exception as exc:  # noqa: BLE001
                status = "failed"
                print(f"  FAILED {dest.name}: {exc}")
            results[status] = results.get(status, 0) + 1
            if status == "ok":
                print(f"  ok     {dest.relative_to(opts['out_dir'])}")

    return results
