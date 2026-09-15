# AGENTS.md

## Project

Coursera scraper: downloads lecture videos, transcripts and readings for courses the
account is enrolled in, into `downloads/<course-slug>/...`. `OBJECTIVE.md` is the full
spec; `README.md` documents usage. See `docs/adr/` for technical decisions.

## Architecture (API-first, no browser)

Talks directly to Coursera's internal `api.coursera.org/api/onDemand*` endpoints — the
same ones the SPA calls. Media URLs are pre-signed, so downloads work without login.

- `src/coursera_scraper/api.py` — endpoints + client (`CourseraClient`).
- `src/coursera_scraper/downloader.py` — URL resolution + parallel file download.
- `src/coursera_scraper/reading.py` — reading HTML/image/plain-text handling.
- `src/coursera_scraper/cli.py` — `coursera-scraper {auth,download}`.

Key facts an agent would otherwise miss:

- `onDemandCourseMaterials.v1` is **deprecated**; use **`.v2`** (response keys end in
  `.v2`, items use `contentSummary` not `content`).
- Lecture media comes from `onDemandLectureVideos.v1/{courseId}~{itemId}` using the
  **item id** (the `item~<id>` segments in a lesson's `elementIds`), not a video id.
- Transcript URLs are **relative** (`/api/subtitleAssetProxy.v1/...`) and must
  be prefixed with `https://api.coursera.org`. Transcripts come from the
  `subtitlesTxt` field (plain-text) — the `.vtt`/`.srt` variants are intentionally ignored.
- Readings come from `onDemandSupplements.v1/{courseId}~{itemId}?includes=asset`
  (**`includes=asset` is required**); the rendered HTML is in
  `linked.openCourseAssets.v1[0].definition.renderableHtmlWithMetadata.renderableHtml`,
  with images already resolved to signed CloudFront URLs. `metadata.hasAssetBlock`
  flags PDF/asset blocks (rare — none in the courses seen so far).
- Lecture slides/PDFs come from `onDemandLectureAssets.v1/{courseId}~{itemId}`
  (`linked.openCourseAssets.v1[].definition.assetId`), then resolved via
  `assets.v1?ids=<comma-joined>` (returns `name`, `typeName`, `url.url`). Strip any
  trailing `@N` suffix from the asset id.
- Quizzes (`staffGraded`, `ungradedAssignment`) are **NOT** reachable via REST — they
  use the GraphQL gateway and need a `CSRF3-Token` cookie. Skipped; see
  `docs/adr/0002-quiz-limitations.md`.
- Files are numbered **by item position within the lesson** (unified across videos
  and readings), matching the Coursera UI order.
- Item `typeName` handling: `lecture` → video (+ slides/transcript), `supplement` →
  reading; quiz, ungradedLab, coach, … are skipped.

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
