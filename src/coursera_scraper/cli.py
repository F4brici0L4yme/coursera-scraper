"""Command-line interface."""

from __future__ import annotations

import argparse
import getpass
import json
import os
import re
import sys
from pathlib import Path

from .api import CourseraClient, CourseraError
from .downloader import download_course

AUTH_FILE = Path.home() / ".coursera-scraper" / "auth.json"

_LEARN_RE = re.compile(r"/learn/([^/?#]+)")


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
    slug = extract_slug(args.course)
    cauth = load_cauth(args.cauth)
    if not cauth:
        print(
            "warning: no CAUTH cookie found (use --cauth, $COURSERA_CAUTH, or 'auth' command).\n"
            "         Enrollment can't be verified; gated content may fail.",
            file=sys.stderr,
        )

    client = CourseraClient(cauth=cauth)
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

    module_filter = args.module
    if args.module is not None and args.module.isdigit():
        module_filter = int(args.module)

    results = download_course(
        client,
        slug,
        progress=_print_progress,
        module_filter=module_filter,
        resolution=args.resolution,
        lang=args.lang,
        out_dir=Path(args.out),
        include_video=not args.no_video,
        include_transcript=not args.no_transcript,
        include_readings=not args.no_readings,
        include_images=not args.no_images,
        include_slides=not args.no_slides,
        concurrency=args.concurrency,
        cauth=cauth,
    )

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
    p_dl.add_argument("course", help="course URL or slug")
    p_dl.add_argument("--module", help="limit to one module: 1-based index or slug")
    p_dl.add_argument(
        "--resolution", default="best", help="best|1080p|720p|540p|360p|240p (default: best)"
    )
    p_dl.add_argument("--lang", default="en", help="subtitle language code (default: en)")
    p_dl.add_argument("--out", default="downloads", help="output root (default: downloads)")
    p_dl.add_argument("--cauth", help="CAUTH cookie value (overrides env/file)")
    p_dl.add_argument("--no-video", action="store_true", help="skip video downloads")
    p_dl.add_argument("--no-transcript", action="store_true", help="skip transcripts")
    p_dl.add_argument("--no-readings", action="store_true", help="skip readings")
    p_dl.add_argument("--no-images", action="store_true", help="skip images embedded in readings")
    p_dl.add_argument(
        "--no-slides", action="store_true", help="skip slides/PDFs attached to videos"
    )
    p_dl.add_argument("--concurrency", type=int, default=3, help="parallel downloads (default: 3)")
    p_dl.set_defaults(func=cmd_download)

    return parser


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
    args = parser.parse_args(argv)
    if args.command is None:
        return launch_tui()
    try:
        return args.func(args)
    except CourseraError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("\nInterrupted.", file=sys.stderr)
        return 130


if __name__ == "__main__":
    sys.exit(main())
