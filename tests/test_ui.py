"""Smoke tests for the Textual UI (needs the 'ui' extra)."""

import asyncio

import pytest

pytest.importorskip("textual")


def _run(coro):
    return asyncio.run(coro)


def test_course_screen_composes():
    from coursera_scraper.ui import CourseraTUI

    async def go():
        app = CourseraTUI(cauth=None)
        async with app.run_test(size=(110, 40)) as pilot:
            await pilot.pause()
            assert app.screen.query_one("#courses") is not None
            assert app.screen.query_one("#banner") is not None
            assert app.screen.query_one("#search") is not None

    _run(go())


def test_library_screen_lists_downloads(tmp_path):
    from coursera_scraper.ui import CourseraTUI, LibraryScreen

    (tmp_path / "demo" / "01-mod" / "01-les").mkdir(parents=True, exist_ok=True)
    (tmp_path / "demo" / "01-mod" / "01-les" / "01-x-transcript.txt").write_text("t")

    async def go():
        app = CourseraTUI(cauth=None)
        app.state.out_dir = str(tmp_path)
        async with app.run_test(size=(110, 40)) as pilot:
            await pilot.pause()
            await app.push_screen(LibraryScreen())
            await pilot.pause()
            opts = app.screen.query_one("#courses")
            assert opts.option_count == 1

    _run(go())


def test_escape_leaves_input():
    from textual.widgets import Input, OptionList

    from coursera_scraper.ui import CourseraTUI

    async def go():
        app = CourseraTUI(cauth=None)
        async with app.run_test(size=(110, 40)) as pilot:
            await pilot.pause()
            inp = app.screen.query_one("#search", Input)
            inp.focus()
            await pilot.pause(0.1)
            await pilot.press("escape")
            await pilot.pause(0.1)
            assert app.focused is app.screen.query_one("#courses", OptionList)

    _run(go())
