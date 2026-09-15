# AGENTS.md

## Project

Coursera scraper: downloads lecture videos, subtitles and transcripts for courses the
account is enrolled in, into `downloads/<course-slug>/...`. `OBJECTIVE.md` is the full
spec; `README.md` documents usage. See `docs/adr/` for technical decisions.

## Architecture (API-first, no browser)

Talks directly to Coursera's internal `api.coursera.org/api/onDemand*` endpoints — the
same ones the SPA calls. Media URLs are pre-signed, so downloads work without login.

- `src/coursera_scraper/api.py` — endpoints + client (`CourseraClient`).
- `src/coursera_scraper/downloader.py` — URL resolution + parallel file download.
- `src/coursera_scraper/cli.py` — `coursera-scraper {auth,download}`.

Key facts an agent would otherwise miss:

- `onDemandCourseMaterials.v1` is **deprecated**; use **`.v2`** (response keys end in
  `.v2`, items use `contentSummary` not `content`).
- Lecture media comes from `onDemandLectureVideos.v1/{courseId}~{itemId}` using the
  **item id** (the `item~<id>` segments in a lesson's `elementIds`), not a video id.
- Subtitle/transcript URLs are **relative** (`/api/subtitleAssetProxy.v1/...`) and must
  be prefixed with `https://api.coursera.org`.
- Item `typeName == "lecture"` are videos; everything else (supplement, quiz,
  ungradedLab, …) is **out of Phase 1 scope** and skipped.

## Constraints (from OBJECTIVE.md)

- **Incremental scope**: Phase 1 = one module → full course → specialization. Do NOT
  build later phases up front.
- **No fixed `sleep()`s**: (only relevant if browser automation is ever reintroduced)
  use selector/state-based waits and retry with backoff.
- **Session reuse**: `CAUTH` cookie (flag → `$COURSERA_CAUTH` →
  `~/.coursera-scraper/auth.json`). Optional; pre-signed URLs work without it.
- **Organized, consistent output** under `downloads/`.
- Never commit `auth.json`, downloaded content, or signed URLs (see `.gitignore`).

## Commands

Use **uv** (not raw venv/pip — Arch is PEP 668 externally-managed):

```bash
uv sync                                    # creates .venv + installs package
uv sync --extra hls                        # adds yt-dlp for HLS/DASH-only courses
uv run coursera-scraper download <slug-or-url> [--module 1] [--resolution 720p]
uv run coursera-scraper auth               # store CAUTH locally
```

Test without installing: `PYTHONPATH=src python3 -m coursera_scraper download ...`.
