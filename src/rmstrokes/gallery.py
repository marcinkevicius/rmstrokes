"""The gallery: every template and example built for review in one go, with a contact sheet.

    rmstrokes gallery                      # gallery.toml here -> ~/rmstrokes-gallery/<date>-<time>-<commit>/
    rmstrokes gallery -o ~/review/today    # a folder of your choice (new, or empty)
    rmstrokes gallery --with-move          # the Paper Pro Move too
    rmstrokes gallery --dry-run            # what would be built, checked but not written

Every document is written as .rmdoc, as .pdf (strokes printed) and as a PNG of its first page,
into <out>/<group>/<device>/, with an index.html that shows every PNG grouped by group and device.

What gets built:

- every template the registry knows (installed, built-in, and the template files the config
  lists), with its defaults and the intro page: a new template shows up without touching the
  config;
- the design system's specimen (rmstrokes specimen), in each device's design theme;
- every entry in the config's [[examples]]: a template with parameters, a recipe file, or a
  command (a console script of an installed package, run with --device and -o added);
- "How a page is built" (rmstrokes explain) for each template the config's `explain` lists, on
  every device: five pictures from inputs to the finished page, at the top of the contact sheet.

Every device is shown in its design theme (design.THEMES): "default" on the reMarkable 2 and
"color" on the colour devices, for templates that have it, unless the entry sets `theme` itself.
On a colour device a template's own colour theme (Template.color_theme) comes first, and the
sections of recipes get it too.

The config (TOML; paths relative to it):

    devices = ["rm2", "pro"]               # --with-move adds "move"
    groups = ["templates"]                 # the order of the groups in the contact sheet
    explain = ["gaps"]                     # templates shown step by step (names or files)
    templates = [{ path = "examples/my_template.py", group = "mine" }]

    [[examples]]
    group = "mine"                         # the group in the contact sheet
    name = "big"                           # file name stem (unique within the group)
    title = "Three words"                  # caption in the contact sheet (default: the name)
    template = "gaps"                      # ... and its parameters, like a recipe section
    words = ["sun", "rain", "wind"]
    intro = true
    color_params = { }                     # parameters only for colour devices

    [[examples]]
    group = "templates"
    name = "reading"
    recipe = "examples/reading.toml"

    [[examples]]
    group = "mine"
    name = "cli"
    command = ["rmstrokes", "make", "gaps"]    # run in the config's folder
    color_args = ["--theme", "color"]          # arguments only for colour devices
"""
from __future__ import annotations

import contextlib
import html
import io
import re
import subprocess
import time
import tomllib
from dataclasses import dataclass, field
from datetime import datetime
from importlib import metadata
from pathlib import Path
from typing import Any, Callable

from .design import get_style
from .devices import DEVICES, Device, device_key
from .params import SchemaError
from .recipe import Section, build_document, read_recipe_file, recipe_from_dict
from .specimen import specimen_document
from .templates import Template, available_templates, get_template, register_file, template_origin

DEFAULT_ROOT = Path("~/rmstrokes-gallery")
DEFAULT_DEVICES = ("rm2", "pro")
CONFIG_KEYS = ("devices", "groups", "templates", "examples", "explain")
ENTRY_KINDS = ("template", "recipe", "command")  # and "specimen", added by the gallery itself
ENTRY_KEYS = ("group", "name", "title", "intro", "color_params", "color_args")
BUILTIN_GROUP = "templates"
DESIGN_APP = "design system"
EXPLAIN = "How a page is built"
EXPLAIN_ID = "explain"  # its anchor, and what --only takes for it
PNG_SCALE = 2.0  # PDF points -> PNG pixels: about 900 px wide for a reMarkable 2 page


@dataclass
class Entry:
    """One document to build on each device."""

    group: str
    name: str
    title: str
    kind: str              # template | recipe | command | specimen
    source: str            # template name, recipe path or the command line, for the listing
    template: str = ""
    params: dict[str, Any] = field(default_factory=dict)
    intro: bool = False
    color_params: dict[str, Any] = field(default_factory=dict)
    recipe: Path | None = None
    command: list[str] = field(default_factory=list)
    color_args: list[str] = field(default_factory=list)


@dataclass
class Job:
    entry: Entry
    device: Device

    @property
    def folder(self) -> Path:
        return Path(slug(self.entry.group)) / self.device.key

    @property
    def stem(self) -> str:
        return slug(self.entry.name)


@dataclass
class Gallery:
    config: Path
    devices: list[Device]
    groups: list[str]       # in contact-sheet order
    jobs: list[Job]
    explain: list[str] = field(default_factory=list)  # templates for "How a page is built"
    explained: list[Explained] = field(default_factory=list)  # filled by run_gallery


@dataclass
class Explained:
    """One template's explainer on one device: its steps' pictures and text, or the error."""

    source: str
    device: Device
    title: str = ""
    steps: list[tuple[str, str, Path]] = field(default_factory=list)  # (title, markdown, png relative to out)
    error: str | None = None


@dataclass
class Built:
    job: Job
    files: dict[str, Path] = field(default_factory=dict)  # rmdoc, pdf, png (relative to the gallery)
    pages: int = 0
    error: str | None = None
    seconds: float = 0.0


def slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-") or "x"


# --------------------------------------------------------------------------- the config

def load_gallery(config: Path | str, *, with_move: bool = False, only: list[str] | None = None) -> Gallery:
    """Read the config, register its template files and resolve every entry on every device:
    templates found, parameters and recipes valid, commands installed."""
    config = Path(config).expanduser().resolve()
    if not config.is_file():
        raise SchemaError(f"gallery config {config} not found")
    try:
        data = tomllib.loads(config.read_text(encoding="utf-8"))
    except tomllib.TOMLDecodeError as e:
        raise SchemaError(f"{config.name}: {e}") from None
    if bad := sorted(set(data) - set(CONFIG_KEYS)):
        raise SchemaError(f"{config.name}: unknown key(s) {', '.join(bad)} (known: {', '.join(CONFIG_KEYS)})")
    base = config.parent
    keys = [device_key(d) for d in data.get("devices", DEFAULT_DEVICES)]
    if with_move and "move" not in keys:
        keys.append("move")
    devices = [DEVICES[k] for k in dict.fromkeys(keys)]

    file_groups = {}
    for i, raw in enumerate(data.get("templates", []), 1):
        if not isinstance(raw, dict) or "path" not in raw:
            raise SchemaError(f"{config.name}: templates[{i}]: expected {{ path = \"...\", group = \"...\" }}")
        name = register_file(base / raw["path"])
        file_groups[name] = raw.get("group", BUILTIN_GROUP)

    entries = default_entries(file_groups)
    seen = {(e.group, e.name) for e in entries}
    for i, raw in enumerate(data.get("examples", []), 1):
        entry = parse_entry(raw, f"{config.name}: examples[{i}]", base)
        if (entry.group, entry.name) in seen:
            raise SchemaError(f"{config.name}: examples[{i}]: {entry.group}/{entry.name} is already taken")
        seen.add((entry.group, entry.name))
        entries.append(entry)
    explain = data.get("explain", [])
    if not isinstance(explain, list) or not all(isinstance(t, str) for t in explain):
        raise SchemaError(f"{config.name}: explain = [\"template\", ...] (names or template files)")
    for name in explain:
        try:
            get_template(name, base)
        except SchemaError as err:
            raise SchemaError(f"{config.name}: explain: {err}") from None
    if only:
        wanted = {slug(a) for a in only}
        entries = [e for e in entries if slug(e.group) in wanted]
        explain = explain if EXPLAIN_ID in wanted or slug(EXPLAIN) in wanted else []
        if not entries and not explain:
            raise SchemaError(f"no group called {', '.join(only)} in the gallery")

    order = [*data.get("groups", []), *sorted({e.group for e in entries})]
    groups = [a for a in dict.fromkeys(order) if any(e.group == a for e in entries)]
    entries.sort(key=lambda e: groups.index(e.group))  # stable: the config's order within a group
    jobs = [Job(e, d) for e in entries for d in devices]
    for job in jobs:
        check(job, base)
    return Gallery(config, devices, groups, jobs, list(explain))


def default_entries(file_groups: dict[str, str]) -> list[Entry]:
    """The design system's specimen, and every template in the registry with its defaults and the
    intro page."""
    entries = [Entry(DESIGN_APP, "specimen", "Specimen: every token of the device's theme", "specimen",
                     "rmstrokes specimen")]
    for name in available_templates():
        origin = template_origin(name)
        if origin == "installed":
            group = name
        elif origin == "file" and name in file_groups:
            group = file_groups[name]
        elif origin == "builtin":
            group = BUILTIN_GROUP
        else:
            continue  # registered in this process by something else: not reproducible from the config
        title = get_template(name).title or name
        entries.append(Entry(group, f"{name}-default", f"{title}: defaults + intro", "template",
                             name, template=name, intro=True))
    return entries


def parse_entry(raw: Any, where: str, base: Path) -> Entry:
    if not isinstance(raw, dict):
        raise SchemaError(f"{where}: expected a table")
    kinds = [k for k in ENTRY_KINDS if k in raw]
    if len(kinds) != 1:
        raise SchemaError(f"{where}: give exactly one of {', '.join(ENTRY_KINDS)}")
    kind = kinds[0]
    for key in ("group", "name"):
        if not isinstance(raw.get(key), str) or not raw[key]:
            raise SchemaError(f"{where}: {key} = \"...\" is required")
    common = dict(group=raw["group"], name=raw["name"], title=raw.get("title", raw["name"]), kind=kind)
    rest = {k: v for k, v in raw.items() if k not in (*ENTRY_KEYS, kind)}
    if kind == "template":
        return Entry(**common, source=raw["template"], template=raw["template"], params=rest,
                     intro=bool(raw.get("intro", False)), color_params=dict(raw.get("color_params", {})))
    if rest:
        raise SchemaError(f"{where}: unknown key(s) {', '.join(sorted(rest))} for a {kind} entry")
    if kind == "recipe":
        path = (base / raw["recipe"]).resolve()
        if not path.is_file():
            raise SchemaError(f"{where}: recipe {raw['recipe']} not found")
        return Entry(**common, source=raw["recipe"], recipe=path)
    command = raw["command"]
    if not isinstance(command, list) or not command or not all(isinstance(a, str) for a in command):
        raise SchemaError(f"{where}: command = [\"tool\", \"arg\", ...]")
    return Entry(**common, source=" ".join(command), command=command, color_args=list(raw.get("color_args", [])))


def check(job: Job, base: Path):
    """Resolve a job without building it; raises SchemaError with the entry and device."""
    e, where = job.entry, f"{job.entry.group}/{job.entry.name} ({job.device.key})"
    try:
        if e.kind == "template":
            template_section(e, job.device, base)
        elif e.kind == "recipe":
            load_recipe_for(e, job.device)
        elif e.kind == "specimen":
            get_style(design_theme(job.device), job.device)
        else:
            console_script(e.command[0])
    except (SchemaError, ValueError) as err:
        raise SchemaError(f"{where}: {err}") from None


# --------------------------------------------------------------------------- building

def design_theme(device: Device) -> str:
    """The design theme a device is shown in: colour on the colour devices."""
    return "color" if device.color else "default"


def device_theme(t: Template, device: Device) -> str | None:
    """The theme `t` is built in on `device`: its own colour theme on a colour device, else the
    device's design theme if `t` has it (None: the template's default)."""
    if device.color and t.color_theme:
        return t.color_theme
    theme = design_theme(device)
    return theme if theme in t.themes() else None


def template_section(e: Entry, device: Device, base: Path) -> Section:
    t = get_template(e.template, base)
    values = dict(e.params)
    if device.color:
        values.update(e.color_params)
    if "theme" not in values and (theme := device_theme(t, device)):
        values["theme"] = theme
    return Section(t, t.validate({**values, "device": device.key}, f"{e.group}/{e.name}"))


def load_recipe_for(e: Entry, device: Device):
    """The recipe for this device: on a colour device, the sections whose template has a colour
    theme use it."""
    data = read_recipe_file(e.recipe)
    if device.color and isinstance(data.get("pages"), list):
        pages = []
        for raw in data["pages"]:
            if isinstance(raw, dict) and "template" in raw:
                t = get_template(raw["template"], e.recipe.parent)
                if theme := device_theme(t, device):
                    raw = {**raw, "theme": theme}
            pages.append(raw)
        data = {**data, "pages": pages}
    # The gallery config is your own, so the recipes it lists may use Python template files.
    return recipe_from_dict(data, e.recipe.name, base=e.recipe.parent, device=device.key, source=e.recipe,
                            allow_python=True)


def console_script(name: str) -> Callable[[list[str]], int]:
    found = metadata.entry_points(group="console_scripts", name=name)
    if not found:
        raise SchemaError(f"command {name!r} is not installed (a console script of an installed package)")
    return next(iter(found)).load()


def build_job(job: Job, out: Path, base: Path) -> Built:
    """Write <out>/<group>/<device>/<name>.rmdoc, .pdf and .png; errors are kept, not raised."""
    built, start = Built(job), time.perf_counter()
    folder = out / job.folder
    folder.mkdir(parents=True, exist_ok=True)
    rmdoc, pdf = folder / f"{job.stem}.rmdoc", folder / f"{job.stem}.pdf"
    e = job.entry
    try:
        if e.kind == "command":
            built.pages = run_command(e, job.device, rmdoc, pdf, base)
        else:
            if e.kind == "specimen":
                doc = specimen_document(job.device, design_theme(job.device))
                namespace = "rmstrokes-specimen"
            elif e.kind == "template":
                section = template_section(e, job.device, base)
                doc = build_document([section], job.device, intro=e.intro)
                doc.title = e.title
                namespace = section.template.seed_namespace
            else:
                recipe = load_recipe_for(e, job.device)
                doc = build_document(recipe.sections, recipe.device, name=recipe.name, intro=recipe.intro)
                doc.title = recipe.name or e.title
                namespace = recipe.sections[0].template.seed_namespace
            doc.write(rmdoc, "rmdoc", namespace=namespace)
            doc.write(pdf, "pdf")
            built.pages = len(doc.pages)
        built.files = {"rmdoc": rmdoc, "pdf": pdf}
        if png := first_page_png(pdf, folder / f"{job.stem}.png"):
            built.files["png"] = png
        built.files = {k: p.relative_to(out) for k, p in built.files.items()}
    except Exception as err:  # one broken document shouldn't stop the review of the others
        built.error = f"{type(err).__name__}: {err}"
    built.seconds = time.perf_counter() - start
    return built


def run_command(e: Entry, device: Device, rmdoc: Path, pdf: Path, base: Path) -> int:
    main = console_script(e.command[0])
    extra = ["--device", device.key, *(e.color_args if device.color else [])]
    for out in (rmdoc, pdf):
        log = io.StringIO()
        with contextlib.chdir(base), contextlib.redirect_stdout(log), contextlib.redirect_stderr(log):
            try:
                code = main([*e.command[1:], *extra, "-o", str(out)])
            except SystemExit as exit_:
                code = exit_.code
        if code or not out.is_file():
            raise RuntimeError(f"{' '.join(e.command)} failed ({code}): {log.getvalue().strip()[-500:]}")
    return pdf_pages(pdf)


def pdf_pages(pdf: Path) -> int:
    try:
        import pypdfium2 as pdfium
    except ImportError:
        return 0
    return len(pdfium.PdfDocument(pdf))


def first_page_png(pdf: Path, png: Path) -> Path | None:
    """The PDF's first page as a PNG (needs pypdfium2; None without it)."""
    try:
        import pypdfium2 as pdfium
    except ImportError:
        return None
    page = pdfium.PdfDocument(pdf)[0]
    page.render(scale=PNG_SCALE).to_pil().save(png, optimize=True)
    return png


def explain_job(source: str, device: Device, out: Path, base: Path) -> Explained:
    """The explainer's pictures into <out>/explain/<device>/; errors are kept, not raised."""
    from .explain import explain, write_explainers
    shown = Explained(source, device)
    try:
        ex = explain(source, device, base=base)
        shown.title = ex.template.title or ex.template.name
        folder = out / EXPLAIN_ID / device.key
        write_explainers([ex], folder, documents=False)
        shown.steps = [(f"{s.n}. {s.title}", s.text, (folder / s.file_name(ex.stem)).relative_to(out))
                       for s in ex.steps]
    except Exception as err:  # like a document: one failure shouldn't stop the review
        shown.error = f"{type(err).__name__}: {err}"
    return shown


# --------------------------------------------------------------------------- the run

def git_label(folder: Path) -> str:
    """Short commit of the checkout the config lives in, '+dirty' with uncommitted changes."""
    def git(*args):
        return subprocess.run(["git", "-C", str(folder), *args], capture_output=True, text=True, check=True).stdout
    try:
        sha = git("rev-parse", "--short", "HEAD").strip()
        dirty = bool(git("status", "--porcelain", "--untracked-files=no").strip())
    except (OSError, subprocess.CalledProcessError):
        return ""
    return sha + ("+dirty" if dirty else "")


def default_out(config: Path, root: Path = DEFAULT_ROOT) -> Path:
    """A new folder per run: <root>/<date>-<time>-<sha>, never one that exists."""
    stamp = datetime.now().strftime("%Y-%m-%d-%H%M")
    label = "-".join(x for x in (stamp, git_label(config.parent)) if x)
    out, n = root.expanduser() / label, 1
    while out.exists():
        n += 1
        out = root.expanduser() / f"{label}-{n}"
    return out


def check_out(out: Path):
    if out.exists() and (not out.is_dir() or any(out.iterdir())):
        raise ValueError(f"{out} isn't an empty folder; the gallery never writes over an earlier one "
                         f"(leave out -o for a new timestamped folder)")


def describe(gallery: Gallery) -> list[str]:
    """The plan, one line per document and device."""
    lines = []
    for source in gallery.explain:
        for device in gallery.devices:
            note = "" if device.verified else "  [unverified device]"
            lines.append(f"{EXPLAIN_ID:<16} {device.key:<5} {slug(source):<28} explain: {source}{note}")
    for job in gallery.jobs:
        note = "" if job.device.verified else "  [unverified device]"
        lines.append(f"{job.entry.group:<16} {job.device.key:<5} {job.entry.name:<28} "
                     f"{job.entry.kind}: {job.entry.source}{note}")
    return lines


def run_gallery(gallery: Gallery, out: Path, log: Callable[[str], None] = print) -> list[Built]:
    check_out(out)
    out.mkdir(parents=True, exist_ok=True)
    results = []
    gallery.explained = [explain_job(source, device, out, gallery.config.parent)
                         for source in gallery.explain for device in gallery.devices]
    for x in gallery.explained:
        status = f"ERROR {x.error}" if x.error else f"{len(x.steps)} steps"
        log(f"{EXPLAIN_ID}/{x.device.key}/{slug(x.source)}: {status}")
    write_index(gallery, results, out)
    for i, job in enumerate(gallery.jobs, 1):
        built = build_job(job, out, gallery.config.parent)
        results.append(built)
        status = f"ERROR {built.error}" if built.error else f"{built.pages} page(s)"
        log(f"[{i}/{len(gallery.jobs)}] {job.entry.group}/{job.device.key}/{job.stem}: {status} "
            f"({built.seconds:.1f} s)")
        write_index(gallery, results, out)  # kept current, so a long run can be looked at early
    return results


# --------------------------------------------------------------------------- the contact sheet

CSS = """
:root { --bg: #f6f5f2; --card: #fff; --ink: #1d1d1b; --muted: #6b6b66; --line: #dcdad4; --warn: #9a5b00;
        --err: #b3261e; --link: #2b5d9b; }
@media (prefers-color-scheme: dark) {
  :root { --bg: #1b1b1a; --card: #262624; --ink: #eceae4; --muted: #a3a29c; --line: #3a3a37; --warn: #e0a24a;
          --err: #f2b8b5; --link: #9cc3f5; } }
* { box-sizing: border-box; }
body { margin: 0; padding: 24px 16px 48px; background: var(--bg); color: var(--ink);
       font: 15px/1.45 -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; }
header, section { max-width: 1400px; margin: 0 auto; }
h1 { font-size: 22px; margin: 0 0 4px; } h2 { font-size: 19px; margin: 36px 0 4px; border-bottom: 1px solid var(--line); }
h3 { font-size: 15px; margin: 18px 0 10px; color: var(--muted); font-weight: 600; }
.meta, nav { color: var(--muted); } nav a { margin-right: 12px; } a { color: var(--link); }
.unverified { color: var(--warn); font-weight: 500; }
.grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(220px, 1fr)); gap: 16px; }
.card { background: var(--card); border: 1px solid var(--line); border-radius: 8px; padding: 10px; }
.card img { display: block; width: 100%; height: auto; background: #fff; border: 1px solid var(--line); }
.card .title { font-weight: 600; margin-top: 8px; } .card .src { color: var(--muted); font-size: 12px;
  word-break: break-all; } .card .files a { margin-right: 10px; font-size: 13px; }
.error { color: var(--err); font-size: 13px; white-space: pre-wrap; word-break: break-word; }
.steps { display: grid; gap: 20px; } .step { background: var(--card); border: 1px solid var(--line);
  border-radius: 8px; padding: 12px; margin: 0; } .step img { display: block; max-width: 100%; height: auto; }
.step figcaption { margin-top: 8px; max-width: 80ch; } .intro { max-width: 80ch; }
code { font-size: 13px; }
"""


def write_index(gallery: Gallery, results: list[Built], out: Path) -> Path:
    e = html.escape
    label = git_label(gallery.config.parent)
    failed = sum(1 for b in results if b.error)
    explain_link = f"<a href=#{EXPLAIN_ID}>{e(EXPLAIN)}</a>" if gallery.explain else ""
    parts = [f"<!doctype html><html lang='en'><head><meta charset='utf-8'>"
             f"<meta name='viewport' content='width=device-width, initial-scale=1'>"
             f"<title>rmstrokes gallery</title><style>{CSS}</style></head><body><header>"
             f"<h1>rmstrokes gallery</h1><p class='meta'>{datetime.now():%Y-%m-%d %H:%M}"
             f"{f' · commit {e(label)}' if label else ''} · {len(results)} of {len(gallery.jobs)} documents"
             f"{f' · <span class=error>{failed} failed</span>' if failed else ''} · config {e(str(gallery.config))}</p>"
             f"<nav>{explain_link}{''.join(f'<a href=#{slug(a)}>{e(a)}</a>' for a in gallery.groups)}</nav></header>"]
    parts += explain_section(gallery)
    for group in gallery.groups:
        parts.append(f"<section id='{slug(group)}'><h2>{e(group)}</h2>")
        for device in gallery.devices:
            cards = [b for b in results if b.job.entry.group == group and b.job.device.key == device.key]
            if not cards:
                continue
            note = "" if device.verified else " <span class=unverified>unverified on a real tablet</span>"
            parts.append(f"<h3>{e(device.name)}{note}</h3><div class=grid>")
            parts += [card(b) for b in cards]
            parts.append("</div>")
        parts.append("</section>")
    parts.append("</body></html>\n")
    index = out / "index.html"
    index.write_text("".join(parts), encoding="utf-8")
    return index


def explain_section(gallery: Gallery) -> list[str]:
    """How a page is built: each explained template's steps, a figure per step, per device."""
    if not gallery.explained:
        return []
    from .explain import INTRO, html_text
    e = html.escape
    parts = [f"<section id='{EXPLAIN_ID}'><h2>{e(EXPLAIN)}</h2><p class=intro>{html_text(INTRO)}</p>"]
    for x in gallery.explained:
        note = "" if x.device.verified else " <span class=unverified>unverified on a real tablet</span>"
        parts.append(f"<h3>{e(x.title or x.source)} · {e(x.device.name)}{note}</h3>")
        if x.error:
            parts.append(f"<div class=error>{e(x.error)}</div>")
            continue
        parts.append("<div class=steps>")
        for title, text, png in x.steps:
            src = e(png.as_posix())
            parts.append(f"<figure class=step><a href='{src}'><img src='{src}' alt='{e(title)}' loading=lazy></a>"
                         f"<figcaption><b>{e(title)}</b> {html_text(text)}</figcaption></figure>")
        parts.append("</div>")
    parts.append("</section>")
    return parts


def card(b: Built) -> str:
    e, entry = html.escape, b.job.entry
    link = {k: e(p.as_posix()) for k, p in b.files.items()}
    img = f"<a href='{link['png']}'><img src='{link['png']}' alt='{e(entry.title)}' loading=lazy></a>" \
        if "png" in link else ""
    files = " ".join(f"<a href='{link[k]}'>.{k}</a>" for k in ("rmdoc", "pdf", "png") if k in link)
    body = f"<div class=error>{e(b.error)}</div>" if b.error else \
        f"<div class=files>{files}</div><div class=src>{b.pages} page(s)</div>"
    return (f"<div class=card>{img}<div class=title>{e(entry.title)}</div>"
            f"<div class=src>{e(entry.kind)}: {e(entry.source)}</div>{body}</div>")
