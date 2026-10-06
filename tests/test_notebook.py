from coursera_scraper import notebook
from coursera_scraper.notebook import _pretty, _title_for, upload_course


def test_pretty():
    assert _pretty("hello-world") == "hello world"
    assert _pretty("foo_bar") == "foo bar"


def test_title_for():
    assert (
        _title_for("01-intro-transcript", 3, "ensemble-learning")
        == "03 ensemble learning / 01 intro (transcript)"
    )
    assert _title_for("02-overview-reading", 1, "svm") == "01 svm / 02 overview (reading)"
    assert _title_for("03-deck-slides-2", 1, "svm") == "01 svm / 03 deck (slides 2)"


def _make_course(tmp_path):
    (tmp_path / "demo" / "01-mod-a" / "01-les").mkdir(parents=True, exist_ok=True)
    (tmp_path / "demo" / "01-mod-a" / "01-les" / "01-x-transcript.txt").write_text("t")
    (tmp_path / "demo" / "01-mod-a" / "01-les" / "02-y-reading.txt").write_text("r")


def _fake_nlm(state):
    def run(*args, profile=None):
        args = list(args)
        if args[:2] == ["notebook", "list"]:
            return [{"id": n["id"], "title": n["title"]} for n in state["notebooks"]]
        if args[:2] == ["notebook", "create"]:
            nb = {"id": "nb1", "title": args[2]}
            state["notebooks"].append(nb)
            return {"notebook_id": "nb1", "title": args[2]}
        if args[:2] == ["source", "list"]:
            return [{"id": s["id"], "title": s["title"]} for s in state["sources"].get(args[2], [])]
        if args[:2] == ["source", "add"]:
            title = args[args.index("--title") + 1]
            nb = args[2]
            src = {"id": f"src{len(state['sources'].get(nb, [])) + 1}", "title": title}
            state["sources"].setdefault(nb, []).append(src)
            return {"source_id": src["id"], "title": title}
        raise AssertionError(args)

    return run


def test_upload_course_creates_single_notebook(monkeypatch, tmp_path):
    _make_course(tmp_path)
    state = {"notebooks": [], "sources": {}}
    monkeypatch.setattr(notebook, "run_nlm", _fake_nlm(state))
    r = upload_course(tmp_path, "demo")
    assert r["ok"] == 2 and r["failed"] == 0
    assert len(state["notebooks"]) == 1
    assert state["notebooks"][0]["title"] == "demo"
    assert len(state["sources"]["nb1"]) == 2


def test_upload_course_idempotent(monkeypatch, tmp_path):
    _make_course(tmp_path)
    state = {"notebooks": [], "sources": {}}
    monkeypatch.setattr(notebook, "run_nlm", _fake_nlm(state))
    upload_course(tmp_path, "demo")
    r2 = upload_course(tmp_path, "demo")
    assert r2["skip"] == 2 and r2["ok"] == 0 and r2["failed"] == 0


def test_upload_course_missing_downloads(tmp_path):
    try:
        upload_course(tmp_path, "nope")
    except notebook.NotebookError as exc:
        assert "No downloads found" in str(exc)
    else:
        raise AssertionError("expected NotebookError")
