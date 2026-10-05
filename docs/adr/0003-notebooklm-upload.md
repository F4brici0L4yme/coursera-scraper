# 3. Gemini Notebook upload via the external `nlm` CLI

- Status: accepted
- Date: 2026-09-17

## Context

After downloading course material, users want it as NotebookLM sources for
study/Q&A. Options were: call NotebookLM's internal RPCs directly from our
code, or shell out to the existing `nlm` CLI (`notebooklm-mcp-cli`).

## Decision

Shell out to `nlm` (`nlm notebook list/create`, `nlm source add/list --json`)
via `subprocess`, with no new Python dependencies. One notebook per course
(named after the course slug; source titles carry the `MM module / NN item`
prefix so the module stays identifiable). Upload `*-transcript.txt`,
`*-reading.txt`, `*-slides-*.pdf`, and attached `.ipynb`; skip `.mp4`
(transcripts carry the spoken content), `.html` twins, reading images, and
`.generic` leftovers. Re-runs skip titles already present.

*Update 2026-10-05: originally one notebook per module; changed to one per
course because many per-module notebooks get unwieldy.*

## Consequences

- Requires the user to install `nlm` (`uv tool install notebooklm-mcp-cli`)
  and run `nlm login` once; our code reports a clear error otherwise.
- We inherit `nlm`'s auth refresh and upload behavior instead of maintaining
  a parallel NotebookLM client.
- JSON parsing is defensive (accepts list or `{items,…}` shapes) since the
  upstream schema is unofficial.
