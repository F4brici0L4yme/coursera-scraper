# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.2.0] - 2026-10-06

### Added

- Lecture videos (best/selectable resolution) and plain-text transcripts.
- Readings as faithful HTML plus `.txt`, with embedded images downloaded and
  rewritten to relative `assets/` paths.
- Lecture slides/PDFs (and attached notebooks) via `onDemandLectureAssets.v1`.
- Interactive TUI (Textual): course search, module selection, options, live
  download progress with throughput/ETA, and a "Mis descargas" library.
- Gemini Notebook (NotebookLM) upload via the external `nlm` CLI: one notebook
  per course, idempotent by source title, plus `notebook --all`. Re-runs use a
  local `.nlm-manifest.json` to skip instantly and upload only new files
  (`--force` re-uploads, `--resync` re-checks against NotebookLM).
- `downloaded` command: local inventory of downloaded courses (`--json`).
- `config` command and `~/.coursera-scraper/config.json` defaults.
- `doctor` command: validates CAUTH, `nlm` login and reports disk space.
- Shell completions via `argcomplete`.
- pytest test suite.
- ADRs documenting API-first design, quiz limitations and NotebookLM upload.

### Changed

- `--module` accepts several modules (index, slug or comma-separated list).
- Source titles carry the `MM module / NN item` prefix so modules stay
  identifiable inside a per-course notebook.

## [0.1.0] - 2026-09-14

### Added

- Initial downloader: lecture videos and captions for courses enrolled in.
