# Coursera Scraper

Downloads videos, subtitles, and transcripts for Coursera courses **your account is
enrolled in**, into an organized local folder tree. No browser automation — it talks
directly to the same internal `onDemand*` API the Coursera web app uses.

## Install (uv)

```bash
uv sync                     # creates .venv, installs deps + the `coursera-scraper` script
uv sync --extra hls         # add yt-dlp for courses that only serve HLS/DASH streams
```

## Auth (optional but recommended)

The API returns pre-signed media URLs, so most content downloads without any cookie.
A `CAUTH` cookie enables enrollment verification and access to gated content.

### Getting your CAUTH cookie

1. Log in to [coursera.org](https://www.coursera.org) in your browser.
2. Open DevTools (`F12`) → **Application** (Chrome) / **Storage** (Firefox) tab →
   **Cookies** → `https://www.coursera.org`.
3. Find the cookie named **`CAUTH`** and copy its **value**.
4. Store it with:

```bash
uv run coursera-scraper auth          # prompts and saves to ~/.coursera-scraper/auth.json
```

Or pass it per-command: `--cauth <value>`, or set `COURSERA_CAUTH=<value>`.
The cookie expires — re-run `auth` when downloads start returning 401/403.

## Usage

```bash
# download a whole course
uv run coursera-scraper download https://www.coursera.org/learn/some-course-slug

# just one module (1-based index or slug)
uv run coursera-scraper download some-course-slug --module 1

# lower resolution to save space
uv run coursera-scraper download some-course-slug --resolution 720p
```

Options: `--module`, `--resolution best|1080p|720p|540p|360p|240p`, `--lang en`,
`--out downloads`, `--concurrency 3`, `--no-video`, `--no-subtitles`, `--no-transcript`.

## Output layout

```
downloads/<course-slug>/<MM>-<module-slug>/<LL>-<lesson-slug>/
    video.mp4              # single-video lesson
    subtitles.en.vtt
    transcript.txt
```

Lessons with several videos use numbered filenames
(`02-<video-slug>-video.mp4`, `02-<video-slug>-subtitles.en.vtt`, …).

## Scope

**Phase 1 (implemented):** lecture videos + subtitles + transcripts.
Quizzes, notebooks, readings and other attachments are detected but skipped.
Full-specialization support is intentionally not built yet.

## Approach

Chosen **API-first** over browser automation — see
[`docs/adr/0001-api-vs-playwright.md`](docs/adr/0001-api-vs-playwright.md) for the
rationale.
