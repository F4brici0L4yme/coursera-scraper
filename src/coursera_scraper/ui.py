"""Interactive terminal UI (Textual) for the scraper.

Launched by running ``coursera-scraper`` with no arguments. Wraps the same
``download_course`` function the CLI uses, so behavior is identical; only the
output surface differs (live progress vs printed lines).
"""

from __future__ import annotations

import json
import re
import shutil
import time
from dataclasses import dataclass, field
from pathlib import Path

from textual import on, work
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.events import DescendantFocus
from textual.screen import ModalScreen, Screen
from textual.widgets import (
    Button,
    Footer,
    Header,
    Input,
    Label,
    LoadingIndicator,
    OptionList,
    ProgressBar,
    RichLog,
    Select,
    SelectionList,
    Static,
    Switch,
)
from textual.widgets.option_list import Option
from textual.widgets.selection_list import Selection

from .api import CourseraClient, CourseraError
from .cli import AUTH_FILE, extract_slug, load_cauth
from .downloader import RESOLUTION_ORDER, download_course
from .inventory import format_size, scan_downloads
from .notebook import NotebookError, upload_course

RESOLUTIONS = ["best", *RESOLUTION_ORDER]

_SLUG_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]*")

CSS = """
Screen {
    background: $surface;
}

#banner {
    color: $accent;
    text-align: center;
    width: 100%;
    padding: 1 2 0 2;
    text-style: bold;
}

#subtitle {
    text-align: center;
    color: $text-muted;
    width: 100%;
    padding: 0 2 1 2;
}

#status {
    color: $text-muted;
    padding: 0 1;
    height: auto;
}

#stats {
    color: $text-muted;
    height: 2;
    padding: 0 1;
}

.hint {
    color: $text-muted;
    padding: 0 1;
}

.field-label {
    color: $text-muted;
    padding: 1 1 0 1;
}

.toggle-row {
    height: 3;
    align: center middle;
}

.toggle-row Label {
    width: 1fr;
}

.actions {
    height: auto;
    align-horizontal: center;
    padding: 1;
}

ProgressBar {
    width: 100%;
}

#summary {
    padding: 1;
}
"""


def _banner() -> str:
    try:
        from pyfiglet import Figlet
    except ImportError:  # pragma: no cover
        return "Coursera Scraper"
    return Figlet(font="slant").renderText("Coursera Scraper").rstrip("\n")


def _fuzzy_match(query: str, text: str) -> bool:
    q = query.strip().lower()
    if not q:
        return True
    it = iter(text.lower())
    return all(ch in it for ch in q)


def _fmt_bytes(n: int) -> str:
    value = float(n)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if value < 1024 or unit == "TB":
            return f"{value:.1f} {unit}" if unit != "B" else f"{int(value)} B"
        value /= 1024
    return f"{value:.1f} TB"


@dataclass
class State:
    slug: str | None = None
    modules: list = field(default_factory=list)
    selected_modules: list = field(default_factory=list)
    resolution: str = "best"
    lang: str = "en"
    include_video: bool = True
    include_transcript: bool = True
    include_readings: bool = True
    include_images: bool = True
    include_slides: bool = True
    out_dir: str = "downloads"
    lib_slug: str | None = None
    lib_modules: list = field(default_factory=list)


class CourseraTUI(App):
    TITLE = "Coursera Scraper"
    CSS = CSS

    def __init__(self, cauth: str | None = None):
        super().__init__()
        self.theme = "nord"
        self.cauth = cauth if cauth is not None else load_cauth(None)
        self.client = CourseraClient(cauth=self.cauth)
        self.state = State()

    def on_mount(self) -> None:
        self.push_screen(CourseScreen())

    def set_cauth(self, value: str) -> None:
        self.cauth = value
        self.client = CourseraClient(cauth=value)


class CourseScreen(Screen):
    BINDINGS = (
        Binding("a", "auth", "Set CAUTH"),
        Binding("d", "library", "Mis descargas"),
        Binding("q", "quit", "Quit"),
        Binding("question_mark", "help", "Help"),
    )

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        yield Static(_banner(), id="banner")
        yield Static("Descarga videos, lecturas y slides de tus cursos", id="subtitle")
        yield Static("", id="status")
        yield Input(placeholder="Buscar curso (o pegar slug / URL)…", id="search")
        yield OptionList(id="courses")
        yield Footer()

    def on_mount(self) -> None:
        self._load_courses()

    def _load_courses(self) -> None:
        status = self.query_one("#status", Static)
        if not self.app.cauth:
            status.update(
                "[dim]Sin CAUTH: pega un slug o URL, o pulsa [bold]a[/] para configurarlo.[/]"
            )
            return
        try:
            courses = self.app.client.enrolled_courses()
        except CourseraError as exc:
            status.update(f"[red]Error al cargar cursos: {exc}[/]")
            return
        if not courses:
            status.update("[dim]No se encontraron cursos enrolados.[/]")
            return
        status.update(
            f"[dim]{len(courses)} cursos enrolados · [bold]a[/] CAUTH · [bold]d[/] mis descargas[/]"
        )
        self._courses = courses
        self._refresh("")

    @on(Input.Changed, "#search")
    def on_search(self, event: Input.Changed) -> None:
        self._refresh(event.value)

    @on(Input.Submitted, "#search")
    def on_search_submitted(self, event: Input.Submitted) -> None:
        text = event.value.strip()
        if not text:
            return
        # Only treat the input as a direct slug/URL if it looks like one;
        # otherwise it's a fuzzy query, so hand focus to the results list.
        if text.startswith("http") or _SLUG_RE.fullmatch(text):
            try:
                slug = extract_slug(text)
            except CourseraError as exc:
                self.query_one("#status", Static).update(f"[red]{exc}[/]")
                return
            self.app.state.slug = slug
            self.app.push_screen(ModulesScreen())
        else:
            opts = self.query_one("#courses", OptionList)
            opts.focus()
            if opts.highlighted is None and opts.option_count:
                opts.highlighted = 0

    def _refresh(self, query: str) -> None:
        courses = getattr(self, "_courses", [])
        opts = self.query_one("#courses", OptionList)
        opts.clear_options()
        for slug, name in courses:
            if _fuzzy_match(query, f"{name} {slug}"):
                opts.add_option(Option(f"{name}  [dim]· {slug}[/]", id=slug))

    @on(DescendantFocus, "#courses")
    def _highlight_first(self) -> None:
        opts = self.query_one("#courses", OptionList)
        if opts.highlighted is None and opts.option_count:
            opts.highlighted = 0

    @on(OptionList.OptionSelected, "#courses")
    def on_course_selected(self, event: OptionList.OptionSelected) -> None:
        self.app.state.slug = event.option_id
        self.app.push_screen(ModulesScreen())

    def action_auth(self) -> None:
        self.app.push_screen(AuthModal())

    def action_library(self) -> None:
        self.app.push_screen(LibraryScreen())

    def action_quit(self) -> None:
        self.app.exit()

    def action_help(self) -> None:
        self.app.push_screen(HelpScreen())


class AuthModal(ModalScreen):
    def compose(self) -> ComposeResult:
        with Vertical(id="dialog"):
            yield Label("Pega tu cookie CAUTH (del navegador, cookie CAUTH de coursera.org):")
            yield Input(password=True, id="cauth-input")
            with Horizontal():
                yield Button("Guardar", variant="primary", id="save")
                yield Button("Cancelar", id="cancel")

    @on(Button.Pressed, "#save")
    def on_save(self) -> None:
        value = self.query_one("#cauth-input", Input).value.strip()
        if value:
            AUTH_FILE.parent.mkdir(parents=True, exist_ok=True)
            AUTH_FILE.write_text(json.dumps({"cauth": value}, indent=2))
            self.app.set_cauth(value)
        self.dismiss()

    @on(Button.Pressed, "#cancel")
    def on_cancel(self) -> None:
        self.dismiss()


class ModulesScreen(Screen):
    BINDINGS = (
        Binding("escape", "back", "Back"),
        Binding("a", "all", "All/None"),
        Binding("enter", "continue", "Continue", priority=True),
    )

    def __init__(self):
        super().__init__()
        self._loaded = False

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        yield Static("Cargando módulos…", id="status")
        yield LoadingIndicator(id="loading")
        yield SelectionList[str](id="modules")
        with Horizontal(classes="actions"):
            yield Button("Continuar", variant="primary", id="continue")
        yield Static("", id="hint", classes="hint")
        yield Footer()

    def on_mount(self) -> None:
        self._resolve()

    @work(thread=True)
    def _resolve(self) -> None:
        try:
            course = self.app.client.get_course(self.app.state.slug)
        except CourseraError as exc:
            self.app.call_from_thread(self._error, str(exc))
            return
        modules = [(m.id, m.slug, m.name) for m in course.modules]
        self.app.state.modules = modules
        self.app.call_from_thread(self._populate, modules)

    def _error(self, message: str) -> None:
        self.query_one("#status", Static).update(f"[red]{message}[/]")
        self.query_one("#loading", LoadingIndicator).display = False

    def _populate(self, modules: list) -> None:
        self.query_one("#loading", LoadingIndicator).display = False
        sel = self.query_one("#modules", SelectionList)
        for mid, mslug, mname in modules:
            sel.add_option(
                Selection(f"{mname}  [dim]· {mslug}[/]", mslug, id=mid, initial_state=True)
            )
        self.query_one("#status", Static).update(
            f"[bold]{len(modules)}[/] módulos · [dim]espacio[/] selecciona · "
            "[dim]a[/] todos/none · [dim]enter[/] continuar"
        )
        self._loaded = True

    def action_all(self) -> None:
        if not self._loaded:
            return
        sel = self.query_one("#modules", SelectionList)
        if sel.selected:
            sel.deselect_all()
        else:
            sel.select_all()

    @on(Button.Pressed, "#continue")
    def on_continue_pressed(self) -> None:
        self.action_continue()

    def action_continue(self) -> None:
        if not self._loaded:
            return
        sel = self.query_one("#modules", SelectionList)
        self.app.state.selected_modules = list(sel.selected)
        self.app.push_screen(OptionsScreen())

    def action_back(self) -> None:
        self.app.pop_screen()


class OptionsScreen(Screen):
    BINDINGS = (
        Binding("escape", "back", "Back"),
        Binding("enter", "start", "Start", priority=True),
    )

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        with VerticalScroll():
            yield Label("Resolución", classes="field-label")
            yield Select([(r, r) for r in RESOLUTIONS], value="best", id="resolution")
            yield Label("Idioma", classes="field-label")
            yield Input(value="en", id="lang")
            yield Label("Directorio de salida", classes="field-label")
            yield Input(value="downloads", id="outdir")
            yield Label("Contenido a descargar", classes="field-label")
            with Horizontal(classes="toggle-row"):
                yield Label("Videos")
                yield Switch(value=True, id="video")
            with Horizontal(classes="toggle-row"):
                yield Label("Transcriptos")
                yield Switch(value=True, id="transcript")
            with Horizontal(classes="toggle-row"):
                yield Label("Lecturas")
                yield Switch(value=True, id="readings")
            with Horizontal(classes="toggle-row"):
                yield Label("Imágenes de lecturas")
                yield Switch(value=True, id="images")
            with Horizontal(classes="toggle-row"):
                yield Label("Slides / PDFs")
                yield Switch(value=True, id="slides")
            with Horizontal(classes="actions"):
                yield Button("Descargar", variant="primary", id="start")
            yield Static("[dim]enter[/] para iniciar · [bold]esc[/] para volver", classes="hint")
        yield Footer()

    @on(Button.Pressed, "#start")
    def on_start_pressed(self) -> None:
        self.action_start()

    def action_start(self) -> None:
        s = self.app.state
        s.resolution = self.query_one("#resolution", Select).value
        s.lang = self.query_one("#lang", Input).value.strip() or "en"
        s.out_dir = self.query_one("#outdir", Input).value.strip() or "downloads"
        s.include_video = self.query_one("#video", Switch).value
        s.include_transcript = self.query_one("#transcript", Switch).value
        s.include_readings = self.query_one("#readings", Switch).value
        s.include_images = self.query_one("#images", Switch).value
        s.include_slides = self.query_one("#slides", Switch).value
        self.app.push_screen(DownloadScreen())

    def action_back(self) -> None:
        self.app.pop_screen()


class DownloadScreen(Screen):
    BINDINGS = (Binding("q", "quit", "Quit"), Binding("escape", "back", "Back"))

    def __init__(self):
        super().__init__()
        self._total = 0
        self._done = 0
        self._bytes = 0
        self._started: float | None = None
        self._finished = False
        self._ok = 0
        self._skip = 0
        self._failed = 0

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        yield Static("Descargando…", id="title")
        yield ProgressBar(id="overall", show_eta=False, show_percentage=True)
        yield Static("", id="stats")
        yield RichLog(id="log", markup=True, highlight=True, wrap=True)
        yield Footer()

    def on_mount(self) -> None:
        self._start()

    @work(thread=True)
    def _start(self) -> None:
        s = self.app.state
        opts = {
            "module_filter": _module_filter(s),
            "resolution": s.resolution,
            "lang": s.lang,
            "out_dir": Path(s.out_dir),
            "include_video": s.include_video,
            "include_transcript": s.include_transcript,
            "include_readings": s.include_readings,
            "include_images": s.include_images,
            "include_slides": s.include_slides,
            "concurrency": 3,
            "cauth": self.app.cauth,
        }
        try:
            results = download_course(self.app.client, s.slug, progress=self._on_progress, **opts)
        except CourseraError as exc:
            self.app.call_from_thread(self._fail, str(exc))
            return
        self.app.call_from_thread(self._finish, results)

    def _on_progress(self, event: dict) -> None:
        self.app.call_from_thread(self._apply_event, event)

    def _apply_event(self, event: dict) -> None:
        t = event["type"]
        if t == "start":
            self._total = event["total"]
            self._started = time.monotonic()
            bar = self.query_one("#overall", ProgressBar)
            bar.total = self._total
            self.query_one("#title", Static).update(
                f"[bold]Descargando[/] {self.app.state.slug} — {self._total} archivos"
            )
        elif t == "bytes":
            self._bytes += event["delta"]
            self._refresh_stats()
        elif t == "file":
            self._done += 1
            if event["status"] == "ok":
                self._ok += 1
            elif event["status"] == "skip":
                self._skip += 1
            else:
                self._failed += 1
            self.query_one("#overall", ProgressBar).progress = self._done
            log = self.query_one("#log", RichLog)
            dest = event["dest"]
            size = _fmt_bytes(event["size"]) if event["size"] else ""
            if event["status"] == "ok":
                log.write(f"[green]✓[/] {dest} [dim]{size}[/]")
            elif event["status"] == "skip":
                log.write(f"[yellow]↷[/] {dest} [dim](ya existe)[/]")
            else:
                log.write(f"[red]✗[/] {dest} [red]{event['error']}[/]")
            self._refresh_stats()

    def _refresh_stats(self) -> None:
        if not self._started:
            return
        elapsed = max(time.monotonic() - self._started, 0.001)
        speed = self._bytes / elapsed
        parts = [f"{_fmt_bytes(self._bytes)} descargados", f"{_fmt_bytes(speed)}/s"]
        if self._done > 0 and self._total > self._done:
            eta = (self._total - self._done) * (elapsed / self._done)
            parts.append(f"ETA {_fmt_duration(eta)}")
        self.query_one("#stats", Static).update(" · ".join(parts))

    def _fail(self, message: str) -> None:
        self._finished = True
        self.query_one("#title", Static).update(f"[red]Error: {message}[/]")

    def _finish(self, results: dict) -> None:
        self._finished = True
        bar = self.query_one("#overall", ProgressBar)
        bar.progress = bar.total or 1
        skipped = results.get("skipped_types") or {}
        summary = (
            f"[bold]Listo.[/] ok={results.get('ok', 0)} "
            f"skip={results.get('skip', 0)} failed={results.get('failed', 0)} "
            f"inline={results.get('inline', 0)}"
        )
        if skipped:
            detail = ", ".join(f"{k}={v}" for k, v in sorted(skipped.items()))
            summary += f"\n[dim]Omitidos (fuera de alcance): {detail}[/]"
        summary += "\n[dim]pulsa [bold]esc[/] para volver, [bold]q[/] para salir[/]"
        self.query_one("#title", Static).update(summary)

    def action_quit(self) -> None:
        self.app.exit()

    def action_back(self) -> None:
        if self._finished:
            self.app.pop_screen()


class LibraryScreen(Screen):
    """Downloaded courses on disk, with upload to Gemini Notebook."""

    BINDINGS = (
        Binding("escape", "back", "Back"),
        Binding("r", "refresh", "Refresh"),
    )

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        yield Static("[bold]Mis descargas[/]", id="subtitle")
        yield Static("", id="status")
        yield OptionList(id="courses")
        yield Footer()

    def on_mount(self) -> None:
        self._refresh()

    def _refresh(self) -> None:
        courses = scan_downloads(self.app.state.out_dir)
        status = self.query_one("#status", Static)
        opts = self.query_one("#courses", OptionList)
        opts.clear_options()
        if not courses:
            status.update(
                f"[dim]No hay descargas en {self.app.state.out_dir}/. Descarga algo primero.[/]"
            )
            return
        status.update(
            f"[dim]{len(courses)} cursos en disco · [bold]enter[/] módulos · "
            "[bold]r[/] refrescar[/]"
        )
        for c in courses:
            nfiles = sum(c["files"].values())
            prompt = (
                f"{c['slug']}  [dim]{len(c['modules'])} mód · "
                f"{nfiles} arch · {format_size(c['size'])}[/]"
            )
            opts.add_option(Option(prompt, id=c["slug"]))

    def action_refresh(self) -> None:
        self._refresh()

    @on(DescendantFocus, "#courses")
    def _highlight_first(self) -> None:
        opts = self.query_one("#courses", OptionList)
        if opts.highlighted is None and opts.option_count:
            opts.highlighted = 0

    @on(OptionList.OptionSelected, "#courses")
    def on_course_selected(self, event: OptionList.OptionSelected) -> None:
        self.app.state.lib_slug = event.option_id
        self.app.push_screen(LibraryModulesScreen())

    def action_back(self) -> None:
        self.app.pop_screen()


class LibraryModulesScreen(Screen):
    BINDINGS = (
        Binding("escape", "back", "Back"),
        Binding("a", "all", "All/None"),
        Binding("enter", "continue", "Continue", priority=True),
    )

    def __init__(self):
        super().__init__()
        self._loaded = False

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        yield Static("Cargando módulos…", id="status")
        yield SelectionList[str](id="modules")
        with Horizontal(classes="actions"):
            yield Button("Subir a NotebookLM", variant="primary", id="continue")
        yield Static("", id="hint", classes="hint")
        yield Footer()

    def on_mount(self) -> None:
        self._populate()

    def _populate(self) -> None:
        slug = self.app.state.lib_slug
        course = next(
            (c for c in scan_downloads(self.app.state.out_dir) if c["slug"] == slug),
            None,
        )
        if course is None:
            self.query_one("#status", Static).update(
                f"[red]Curso no encontrado en disco: {slug}[/]"
            )
            return
        sel = self.query_one("#modules", SelectionList)
        for m in course["modules"]:
            label = (
                f"{m['index']:02d} {m['slug']}  "
                f"[dim]{sum(m['files'].values())} arch · {format_size(m['size'])}[/]"
            )
            sel.add_option(Selection(label, m["slug"], id=str(m["index"]), initial_state=True))
        self.query_one("#status", Static).update(
            f"[bold]{len(course['modules'])}[/] módulos · [dim]espacio[/] selecciona · "
            "[dim]a[/] todos/none · [dim]enter[/] subir"
        )
        self._loaded = True

    def action_all(self) -> None:
        if not self._loaded:
            return
        sel = self.query_one("#modules", SelectionList)
        if sel.selected:
            sel.deselect_all()
        else:
            sel.select_all()

    @on(Button.Pressed, "#continue")
    def on_continue_pressed(self) -> None:
        self.action_continue()

    def action_continue(self) -> None:
        if not self._loaded:
            return
        sel = self.query_one("#modules", SelectionList)
        self.app.state.lib_modules = list(sel.selected)
        self.app.push_screen(NotebookUploadScreen())

    def action_back(self) -> None:
        self.app.pop_screen()


class NotebookUploadScreen(Screen):
    BINDINGS = (Binding("q", "quit", "Quit"), Binding("escape", "back", "Back"))

    def __init__(self):
        super().__init__()
        self._total = 0
        self._done = 0
        self._started: float | None = None
        self._finished = False
        self._ok = 0
        self._skip = 0
        self._failed = 0

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        yield Static("Subiendo a NotebookLM…", id="title")
        yield ProgressBar(id="overall", show_eta=False, show_percentage=True)
        yield Static("", id="stats")
        yield RichLog(id="log", markup=True, highlight=True, wrap=True)
        yield Footer()

    def on_mount(self) -> None:
        self._start()

    @work(thread=True)
    def _start(self) -> None:
        if shutil.which("nlm") is None:
            self.app.call_from_thread(
                self._fail,
                "No se encontró el comando 'nlm'. "
                "Instálalo con: uv tool install notebooklm-mcp-cli",
            )
            return
        s = self.app.state
        filt = list(s.lib_modules) or None
        try:
            results = upload_course(
                s.out_dir,
                s.lib_slug,
                module_filter=filt,
                progress=self._on_progress,
            )
        except NotebookError as exc:
            self.app.call_from_thread(self._fail, str(exc))
            return
        self.app.call_from_thread(self._finish, results)

    def _on_progress(self, event: dict) -> None:
        self.app.call_from_thread(self._apply_event, event)

    def _apply_event(self, event: dict) -> None:
        t = event["type"]
        if t == "start":
            self._total = event["total"]
            self._started = time.monotonic()
            bar = self.query_one("#overall", ProgressBar)
            bar.total = self._total
            self.query_one("#title", Static).update(
                f"[bold]Subiendo[/] {self.app.state.lib_slug} — {self._total} fuentes"
            )
        elif t == "file":
            self._done += 1
            if event["status"] == "ok":
                self._ok += 1
            elif event["status"] == "skip":
                self._skip += 1
            else:
                self._failed += 1
            self.query_one("#overall", ProgressBar).progress = self._done
            log = self.query_one("#log", RichLog)
            dest = event["dest"]
            if event["status"] == "ok":
                log.write(f"[green]✓[/] {dest}")
            elif event["status"] == "skip":
                log.write(f"[yellow]↷[/] {dest} [dim](ya existe)[/]")
            else:
                log.write(f"[red]✗[/] {dest} [red]{event['error']}[/]")

    def _fail(self, message: str) -> None:
        self._finished = True
        self.query_one("#title", Static).update(f"[red]Error: {message}[/]")

    def _finish(self, results: dict) -> None:
        self._finished = True
        bar = self.query_one("#overall", ProgressBar)
        bar.progress = bar.total or 1
        lines = [
            f"[bold]Listo.[/] ok={results.get('ok', 0)} "
            f"skip={results.get('skip', 0)} failed={results.get('failed', 0)}"
        ]
        for nb in results.get("notebooks", []):
            state = "creado" if nb["created"] else "reutilizado"
            lines.append(f"[dim]Notebook {state}: {nb['name']}[/]")
        lines.append("[dim]pulsa [bold]esc[/] para volver, [bold]q[/] para salir[/]")
        self.query_one("#title", Static).update("\n".join(lines))

    def action_quit(self) -> None:
        self.app.exit()

    def action_back(self) -> None:
        if self._finished:
            self.app.pop_screen()


class HelpScreen(Screen):
    BINDINGS = (Binding("escape", "back", "Back"), Binding("q", "back", "Back"))

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        yield Static(
            "[bold]Atajos[/]\n\n"
            "  j / k · ↑ / ↓   mover\n"
            "  enter           seleccionar / continuar\n"
            "  espacio         marcar módulo\n"
            "  a               todos/none (módulos) · configurar CAUTH (cursos)\n"
            "  d               mis descargas (cursos)\n"
            "  r               refrescar (mis descargas)\n"
            "  esc             volver\n"
            "  q               salir\n"
            "  ctrl+p          paleta de comandos\n",
            id="summary",
        )
        yield Footer()

    def action_back(self) -> None:
        self.app.pop_screen()


def _module_filter(s: State):
    return list(s.selected_modules) or None


def _fmt_duration(seconds: float) -> str:
    seconds = int(seconds)
    m, sec = divmod(seconds, 60)
    h, m = divmod(m, 60)
    if h:
        return f"{h}h{m:02d}m"
    return f"{m}m{sec:02d}s"


def run_ui(cauth: str | None = None) -> int:
    """Launch the interactive TUI. Returns the process exit code."""
    app = CourseraTUI(cauth=cauth)
    app.run()
    return 0
