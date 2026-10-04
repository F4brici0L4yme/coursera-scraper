# Coursera Scraper

Downloads videos, transcripts, and readings for Coursera courses **your account is
enrolled in**, into an organized local folder tree. No browser automation — it talks
directly to the same internal `onDemand*` API the Coursera web app uses.

## Install (uv)

```bash
uv sync                     # creates .venv, installs deps + the `coursera-scraper` script
uv sync --extra ui          # add Textual for the interactive TUI
uv sync --extra hls         # add yt-dlp for courses that only serve HLS/DASH streams
```

## Interactive TUI

Run the scraper with no arguments to open the interactive terminal UI:

```bash
uv run coursera-scraper
```

It walks you through: pick a course (search, or paste a slug/URL) → select modules →
choose options (resolution, language, content types) → watch progress with live
throughput and ETA. Requires `uv sync --extra ui`.

The CLI subcommands (`download`, `auth`) remain available for scripting/automation.

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

# just one module (1-based index or slug), or several comma-separated
uv run coursera-scraper download some-course-slug --module 1
uv run coursera-scraper download some-course-slug --module 1,3

# lower resolution to save space
uv run coursera-scraper download some-course-slug --resolution 720p
```

Options: `--module` (index, slug, or comma-separated list), `--resolution best|1080p|720p|540p|360p|240p`, `--lang en`,
`--out downloads`, `--concurrency 3`, `--no-video`, `--no-transcript`,
`--no-readings`, `--no-images`, `--no-slides`.

## Gemini Notebook upload

Send transcripts, readings, slides, and notebooks to Gemini Notebook (formerly
NotebookLM) via the external [`nlm` CLI](https://github.com/jacob-bd/gemini-notebook-mcp-cli).
One notebook is created per module (NotebookLM caps sources per notebook).

```bash
uv tool install notebooklm-mcp-cli   # one-time: provides `nlm`
nlm login                            # one-time: Google login in your browser
nlm login --check                    # verify auth still works

# upload one module (transcripts + readings + slides, videos excluded)
uv run coursera-scraper notebook some-course-slug --module 1

# preview without uploading, or force re-upload / single notebook / other profile
uv run coursera-scraper notebook some-course-slug --module 1 --dry-run
uv run coursera-scraper notebook some-course-slug --module 1 --force
uv run coursera-scraper notebook some-course-slug --module 1 --notebook "Mi Notebook"
```

Re-runs skip sources whose titles already exist in the notebook. Videos (`.mp4`),
reading images, and `.html` twins are not uploaded — transcripts carry the spoken
content and `.txt` readings carry the text.

If uploads start failing with auth errors, re-login (`nlm login`) or refresh
headlessly (`nlm auth refresh`); check status with `nlm login --check`. For a
second Google account, pass `--nlm-profile <name>` (after `nlm login --profile`).

## Output layout

Items are numbered by their position within the lesson (matching the Coursera UI):

```
downloads/<course-slug>/<MM>-<module-slug>/<LL>-<lesson-slug>/
    NN-<video-slug>-video.mp4
    NN-<video-slug>-transcript.txt
    NN-<video-slug>-slides-N.pdf      # slides/PDFs attached to the video (when present)
    NN-<reading-slug>-reading.html      # faithful HTML, images rewritten to assets/
    NN-<reading-slug>-reading.txt       # plain text
    assets/NN-<reading-slug>-img-N.png  # images embedded in the reading
```

## Scope

- **Phase 1 (implemented):** lecture videos + transcripts.
- **Phase 2 (implemented):** readings (as HTML + plain text, with embedded images
  downloaded). Code blocks are preserved in the HTML.
- **Phase 3 (implemented):** slides/PDFs (and attached notebooks) from videos.
- **Notebook upload (implemented):** send transcripts, readings, and slides to
  Gemini Notebook, one notebook per module — see above.
- Quizzes (`staffGraded`/`ungradedAssignment`) and lab workspaces (`ungradedLab`)
  are detected but skipped — see [docs/adr/0002-quiz-limitations.md](docs/adr/0002-quiz-limitations.md).
- Full-specialization support is intentionally not built yet.

## Approach

Chosen **API-first** over browser automation — see
[`docs/adr/0001-api-vs-playwright.md`](docs/adr/0001-api-vs-playwright.md) for the
rationale.
