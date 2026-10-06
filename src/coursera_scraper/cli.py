"""Command-line interface."""

from __future__ import annotations

import argparse
import getpass
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

from .api import CourseraClient, CourseraError
from .config import CONFIG_FILE, DEFAULTS, load_config, resolve, save_config
from .downloader import RESOLUTION_ORDER, download_course
from .inventory import format_size, scan_downloads
from .notebook import NotebookError, upload_course

AUTH_FILE = Path.home() / ".coursera-scraper" / "auth.json"

_LEARN_RE = re.compile(r"/learn/([^/?#]+)")
_SPEC_RE = re.compile(r"/specializations/([^/?#]+)")


def classify_target(arg: str, specialization_flag: bool) -> tuple[str, str]:
    """Return ``("course"|"specialization", slug)`` for a slug or URL."""
    if arg.startswith("http"):
        m = _SPEC_RE.search(arg)
        if m:
            return "specialization", m.group(1)
        return "course", extract_slug(arg)
    slug = arg.strip("/")
    return ("specialization" if specialization_flag else "course"), slug


def _parse_modules(raw: str | None):
    """Parse --module: single index/slug or comma-separated list of them."""
    if raw is None:
        return None
    parts = [p.strip() for p in raw.split(",") if p.strip()]
    if not parts:
        return None
    vals = [int(p) if p.isdigit() else p for p in parts]
    return vals[0] if len(vals) == 1 else vals


def extract_slug(arg: str) -> str:
    if arg.startswith("http"):
        m = _LEARN_RE.search(arg)
        if not m:
            raise CourseraError(f"Could not extract a course slug from URL: {arg}")
        return m.group(1)
    return arg.strip("/")


def load_cauth(cauth_flag: str | None) -> str | None:
    if cauth_flag:
        return cauth_flag
    if os.environ.get("COURSERA_CAUTH"):
        return os.environ["COURSERA_CAUTH"]
    if AUTH_FILE.exists():
        data = json.loads(AUTH_FILE.read_text())
        return data.get("cauth")
    return None


def cmd_auth(args: argparse.Namespace) -> int:
    AUTH_FILE.parent.mkdir(parents=True, exist_ok=True)
    value = args.cauth or getpass.getpass("Paste your CAUTH cookie value: ")
    AUTH_FILE.write_text(json.dumps({"cauth": value.strip()}, indent=2))
    print(f"CAUTH saved to {AUTH_FILE}")
    return 0


def _print_progress(event: dict) -> None:
    if event["type"] == "file":
        if event["status"] == "ok":
            print(f"  ok     {event['dest']}")
        elif event["status"] == "failed":
            print(f"  FAILED {event['dest']}: {event['error']}")


def cmd_download(args: argparse.Namespace) -> int:
    cauth = load_cauth(args.cauth)
    if not cauth:
        print(
            "warning: no CAUTH cookie found (use --cauth, $COURSERA_CAUTH, or 'auth' command).\n"
            "         Enrollment can't be verified; gated content may fail.",
            file=sys.stderr,
        )

    client = CourseraClient(cauth=cauth)
    cfg = load_config()
    kind, slug = classify_target(args.course, args.specialization)
    opts = dict(
        progress=_print_progress,
        module_filter=_parse_modules(args.module),
        resolution=resolve(cfg, "resolution", args.resolution),
        lang=resolve(cfg, "lang", args.lang),
        out_dir=Path(resolve(cfg, "out_dir", args.out)),
        include_video=not args.no_video,
        include_transcript=not args.no_transcript,
        include_readings=not args.no_readings,
        include_images=not args.no_images,
        include_slides=not args.no_slides,
        concurrency=resolve(cfg, "concurrency", args.concurrency),
        cauth=cauth,
    )

    if kind == "specialization":
        name, course_slugs = client.get_specialization(slug)
        if not course_slugs:
            print(f"No courses found in specialization '{name}'.", file=sys.stderr)
            return 1
        print(f"Specialization '{name}': {len(course_slugs)} courses")
        failed = 0
        for i, course_slug in enumerate(course_slugs, 1):
            print(f"\n=== {course_slug} ({i}/{len(course_slugs)}) ===")
            r = download_course(client, course_slug, **opts)
            print(f"Done {course_slug}. ok={r['ok']} skip={r['skip']} failed={r['failed']}")
            failed += 1 if r["failed"] else 0
        return 1 if failed else 0

    print(f"Resolving course '{slug}' ...")
    if cauth:
        try:
            enrolled = client.enrolled_slugs()
            if enrolled and slug not in enrolled:
                print(
                    f"warning: '{slug}' is not in your enrolled courses list. Proceeding anyway.",
                    file=sys.stderr,
                )
        except CourseraError as exc:
            print(f"warning: could not verify enrollment ({exc})", file=sys.stderr)

    results = download_course(client, slug, **opts)
    print(
        f"\nDone. tasks={results['tasks']} ok={results['ok']} "
        f"skipped={results['skip']} failed={results['failed']} "
        f"inline={results['inline']} locked={results['locked']}"
    )
    if results.get("skipped_types"):
        detail = ", ".join(f"{k}={v}" for k, v in sorted(results["skipped_types"].items()))
        print(f"Skipped items (out of scope): {detail}")
    return 1 if results["failed"] else 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="coursera-scraper",
        description="Download Coursera course media. Run with no command for the interactive TUI.",
    )
    sub = parser.add_subparsers(dest="command")

    p_auth = sub.add_parser("auth", help="save the CAUTH cookie locally")
    p_auth.add_argument("--cauth", help="CAUTH cookie value (prompts if omitted)")
    p_auth.set_defaults(func=cmd_auth)

    p_dl = sub.add_parser("download", help="download a course (or one module)")
    p_dl.add_argument("course", help="course/specialization URL or slug")
    p_dl.add_argument(
        "--specialization",
        action="store_true",
        help="treat the argument as a specialization slug (download all its courses)",
    )
    p_dl.add_argument(
        "--module",
        help="limit to modules: 1-based index, slug, or comma-separated list (e.g. 1,3)",
    )
    p_dl.add_argument(
        "--resolution",
        default=None,
        choices=["best", *RESOLUTION_ORDER],
        help="best|1080p|720p|540p|360p|240p (default: config or best)",
    )
    p_dl.add_argument("--lang", default=None, help="subtitle language code (default: config or en)")
    p_dl.add_argument("--out", default=None, help="output root (default: config or downloads)")
    p_dl.add_argument("--cauth", help="CAUTH cookie value (overrides env/file)")
    p_dl.add_argument("--no-video", action="store_true", help="skip video downloads")
    p_dl.add_argument("--no-transcript", action="store_true", help="skip transcripts")
    p_dl.add_argument("--no-readings", action="store_true", help="skip readings")
    p_dl.add_argument("--no-images", action="store_true", help="skip images embedded in readings")
    p_dl.add_argument(
        "--no-slides", action="store_true", help="skip slides/PDFs attached to videos"
    )
    p_dl.add_argument(
        "--concurrency", type=int, default=None, help="parallel downloads (default: config or 3)"
    )
    p_dl.set_defaults(func=cmd_download)

    p_nb = sub.add_parser(
        "notebook", help="upload downloaded material to Gemini Notebook (via nlm)"
    )
    p_nb.add_argument(
        "course",
        nargs="?",
        default=None,
        help="course URL or slug (omit with --all; must already be downloaded)",
    )
    p_nb.add_argument("--all", action="store_true", help="upload every downloaded course")
    p_nb.add_argument(
        "--module",
        help="limit to modules: 1-based index, slug, or comma-separated list (e.g. 1,3)",
    )
    p_nb.add_argument("--out", default="downloads", help="download root to read from")
    p_nb.add_argument(
        "--notebook",
        default=None,
        help="notebook name (default: the course slug)",
    )
    p_nb.add_argument(
        "--dry-run", action="store_true", help="list what would be uploaded without calling nlm"
    )
    p_nb.add_argument(
        "--force",
        action="store_true",
        help="re-upload even if a source with the same title exists",
    )
    p_nb.add_argument(
        "--no-wait", action="store_true", help="don't wait for NotebookLM source processing"
    )
    p_nb.add_argument("--nlm-profile", default=None, help="nlm profile to use")
    p_nb.set_defaults(func=cmd_notebook)

    p_ls = sub.add_parser("downloaded", help="list locally downloaded courses")
    p_ls.add_argument("--out", default="downloads", help="download root to scan")
    p_ls.add_argument("--json", action="store_true", help="output as JSON")
    p_ls.set_defaults(func=cmd_downloaded)

    p_cfg = sub.add_parser("config", help="set default options (stored in config.json)")
    p_cfg.add_argument(
        "--resolution", default=None, choices=["best", *RESOLUTION_ORDER], help="default resolution"
    )
    p_cfg.add_argument("--lang", default=None, help="default subtitle language")
    p_cfg.add_argument("--out", default=None, help="default output root")
    p_cfg.add_argument("--concurrency", type=int, default=None, help="default concurrency")
    p_cfg.set_defaults(func=cmd_config)

    p_doc = sub.add_parser("doctor", help="diagnose auth, nlm, config, and disk")
    p_doc.set_defaults(func=cmd_doctor)

    return parser


def cmd_config(args: argparse.Namespace) -> int:
    save_config(
        {
            "resolution": args.resolution,
            "lang": args.lang,
            "out_dir": args.out,
            "concurrency": args.concurrency,
        }
    )
    print(f"Config saved to {CONFIG_FILE}")
    for key in sorted(DEFAULTS):
        print(f"  {key} = {load_config().get(key, DEFAULTS[key])}")
    return 0


def cmd_doctor(args: argparse.Namespace) -> int:
    cfg = load_config()
    print(f"Config: {CONFIG_FILE if CONFIG_FILE.exists() else '(none)'}")
    for key in sorted(DEFAULTS):
        print(f"  {key} = {cfg.get(key, DEFAULTS[key])}")

    cauth = load_cauth(None)
    print("CAUTH:", "present" if cauth else "missing")
    if cauth:
        try:
            n = len(CourseraClient(cauth=cauth).enrolled_slugs())
            print(f"  valid — {n} enrolled courses")
        except CourseraError as exc:
            print(f"  invalid/expired: {exc}")

    nlm = shutil.which("nlm")
    print("nlm:", nlm or "not found (uv tool install notebooklm-mcp-cli)")
    if nlm:
        try:
            proc = subprocess.run(
                [nlm, "login", "--check"], capture_output=True, text=True, timeout=60
            )
        except (OSError, subprocess.TimeoutExpired):
            proc = None
        if proc is None:
            print("  login --check: failed to run")
        else:
            print(f"  login --check: rc={proc.returncode}")
            if proc.returncode != 0:
                print("  ", (proc.stdout or proc.stderr).strip()[-200:])

    out = cfg.get("out_dir", DEFAULTS["out_dir"])
    try:
        usage = shutil.disk_usage(out)
        free = usage.free // (1024**3)
        total = usage.total // (1024**3)
        print(f"disk ({out}): {free} GiB free / {total} GiB")
    except OSError:
        print(f"disk ({out}): unavailable")
    return 0


def cmd_downloaded(args: argparse.Namespace) -> int:
    courses = scan_downloads(args.out)
    if args.json:
        print(json.dumps({"root": args.out, "courses": courses}, indent=2))
        return 0
    if not courses:
        print(f"No downloaded courses found in {args.out}/.")
        return 0
    width = min(max(len(c["slug"]) for c in courses), 48)
    header = (
        f"{'course':<{width}}  {'mod':>3}  {'files':>5}  {'vid':>3}  "
        f"{'trs':>3}  {'rdg':>3}  {'sld':>3}  {'img':>3}  {'size':>8}"
    )
    print(f"Downloaded courses (root: {args.out}/):")
    print(header)
    for c in courses:
        f = c["files"]
        line = (
            f"{c['slug']:<{width}.{width}}  {len(c['modules']):>3}  "
            f"{sum(f.values()):>5}  {f.get('videos', 0):>3}  {f.get('transcripts', 0):>3}  "
            f"{f.get('readings', 0):>3}  {f.get('slides', 0):>3}  {f.get('images', 0):>3}  "
            f"{format_size(c['size']):>8}"
        )
        print(line)
        for m in c["modules"]:
            print(f"  {m['index']:02d}-{m['slug']}")
    return 0


def cmd_notebook(args: argparse.Namespace) -> int:
    if args.course is None and not args.all:
        print("error: need a course or --all", file=sys.stderr)
        return 2
    if args.course is not None:
        slugs = [extract_slug(args.course)]
    else:
        slugs = [c["slug"] for c in scan_downloads(args.out)]
        if not slugs:
            print(f"No downloaded courses found in {args.out}/.", file=sys.stderr)
            return 1
    filt = _parse_modules(args.module)
    total = {"ok": 0, "skip": 0, "failed": 0}
    failed = 0
    for n, slug in enumerate(slugs):
        if len(slugs) > 1:
            print(f"\n=== {slug} ({n + 1}/{len(slugs)}) ===")
        try:
            results = upload_course(
                args.out,
                slug,
                progress=_print_progress,
                module_filter=filt,
                notebook=args.notebook,
                dry_run=args.dry_run,
                force=args.force,
                wait=not args.no_wait,
                profile=args.nlm_profile,
            )
        except (CourseraError, NotebookError) as exc:
            print(f"FAILED {slug}: {exc}", file=sys.stderr)
            failed += 1
            continue
        for nb in results["notebooks"]:
            print(f"{'created' if nb['created'] else 'reused'} notebook: {nb['name']}")
        print(
            f"Done {slug}. ok={results['ok']} skipped={results['skip']} failed={results['failed']}"
        )
        for key in total:
            total[key] += results[key]
        failed += 1 if results["failed"] else 0
    if len(slugs) > 1:
        print(f"\nTotal. ok={total['ok']} skipped={total['skip']} failed={total['failed']}")
    return 1 if failed else 0


def launch_tui() -> int:
    try:
        from .ui import run_ui
    except ImportError:
        print(
            "The interactive TUI requires the 'textual' package.\n"
            "Install it with:  uv sync --extra ui",
            file=sys.stderr,
        )
        return 1
    return run_ui()


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    try:
        import argcomplete

        argcomplete.autocomplete(parser)
    except ImportError:  # pragma: no cover - optional
        pass
    args = parser.parse_args(argv)
    if args.command is None:
        return launch_tui()
    try:
        return args.func(args)
    except (CourseraError, NotebookError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("\nInterrupted.", file=sys.stderr)
        return 130


if __name__ == "__main__":
    sys.exit(main())
