"""How a page is built, step by step, in pictures: `rmstrokes explain`.

    rmstrokes explain                                   # the built-in gaps template, rm2 -> ./explain/
    rmstrokes explain gaps my_page.toml --device all -o out/
    rmstrokes explain gaps examples/character_mix/character_mix.py \\
        -o docs/how-a-page-is-built --markdown docs/how-a-page-is-built.md

Five steps, each a PNG drawn from the template's real first page (its defaults unless values are
given), so the pictures are what the engine does, not a diagram of it:

1. inputs: the template and its parameter values (text), and the shapes or SVG files of its tokens;
2. layout: the boxes the template works out in device px, and the PDF background drawn from them;
3. strokes: one token, from its shape or SVG to the pen strokes it becomes;
4. layers: the PDF background and each stroke layer on its own, bottom to top;
5. finished: the page as printed (PDF export) and what the .rmdoc holds.

The text of each step is written here as well (markdown), so the command, the gallery's
"How a page is built" section (`explain = [...]` in gallery.toml) and docs/how-a-page-is-built.md
all say the same. The layout and strokes steps use what a template lists in `Page.meta`
("areas" and "placements", see tokens.Placement): data templates do; a Python template that
doesn't gets the plainer pictures. PNGs need pypdfium2, like the specimen's.
"""
from __future__ import annotations

import html
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Sequence

from PIL import Image, ImageDraw, ImageFont

from .design import SANS, SANS_SEMIBOLD
from .devices import Device, get_device
from .fonts import font_path
from .geometry import page_size
from .layers import Document, Page
from .pdf import STROKE_COLORS
from .recipe import Section, build_document
from .shapes import shape_region
from .templates import COMMON_NAMES, Template, get_template, template_origin
from .tokens import Placement
from .vectorize import Stroke, load_art

STEPS = (
    ("inputs", "What goes in"),
    ("layout", "Layout"),
    ("strokes", "Shapes and SVGs become pen strokes"),
    ("layers", "Layers"),
    ("finished", "The finished page"),
)
TITLE = "How a page is built"
INTRO = ("Every page is a fixed PDF background plus named layers of real pen strokes. A template turns its "
         "parameter values (text) and its tokens' shapes or SVG files into both: it lays the page out, "
         "draws the background with reportlab, turns each token into one compact cluster of strokes, "
         "puts the clusters on layers and writes the result as an `.rmdoc` notebook (strokes movable) or "
         "a plain PDF (strokes printed). The pictures below are drawn from the template's own page.")

# Sheet layout, in sheet px.
PANEL_H = 720           # a portrait page panel's height (fewer px when a step has many panels)
PANEL_MAX_W = 760
GAP = 64                # between panels (an arrow or a plus sits in it)
PAD = 32
INK, MUTED, LINE, PAPER = "#1d1d1b", "#6b6b66", "#c9c7c1", "#ffffff"
SHEET = "#f6f5f2"
ACCENT, WARN = "#2b5d9b", "#9a5b00"
# Per-stroke colours in the strokes step (distinct, readable on white).
WHITE_INK = "#dcdad4"
HUES = ("#2b5d9b", "#c0392b", "#2e8b3e", "#b0359a", "#d17a00", "#1fa5c2", "#6d4c9f", "#8a6d1d")


@dataclass
class Step:
    n: int
    key: str
    title: str
    text: str                      # markdown: `code` and plain sentences
    image: Image.Image | None = None

    def file_name(self, stem: str) -> str:
        return f"{stem}-{self.n}-{self.key}.png"


@dataclass
class Explainer:
    source: str                    # the template as asked for (a name or a path)
    template: Template
    device: Device
    values: dict[str, Any]
    doc: Document                  # one page: the template's first
    steps: list[Step] = field(default_factory=list)

    @property
    def page(self) -> Page:
        return self.doc.pages[0]

    @property
    def stem(self) -> str:
        return f"{slug(self.template.name)}-{self.device.key}"

    @property
    def heading(self) -> str:
        return f"{self.template.title or self.template.name} (`{self.template.name}`) on the {self.device.name}"


def slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-") or "x"


# --------------------------------------------------------------------------- the steps

def explain(template: str | Path | Template, device: Device | str = "rm2", values: dict[str, Any] | None = None,
            *, render: bool = True, base: Path | None = None) -> Explainer:
    """The five steps for `template`'s first page on `device`; `render=False` leaves out the
    pictures (the text alone, for checking the docs)."""
    from .gallery import device_theme
    t = get_template(template, base)
    device = get_device(device)
    values = dict(values or {})
    if "theme" not in values and (theme := device_theme(t, device)):
        values["theme"] = theme  # the colour theme on a colour device, like the gallery
    values = t.validate({**values, "device": device.key})
    doc = build_document([Section(t, values)], device, name=values["name"])
    doc.pages = doc.pages[:1]
    doc.title = values["name"] or t.default_title or t.title or t.name
    ex = Explainer(str(template.name if isinstance(template, Template) else template), t, device, values, doc)
    texts = {"inputs": _inputs_text, "layout": _layout_text, "strokes": _strokes_text, "layers": _layers_text,
             "finished": _finished_text}
    images = {"inputs": _inputs_image, "layout": _layout_image, "strokes": _strokes_image,
              "layers": _layers_image, "finished": _finished_image}
    pages = _Pages(ex)
    for n, (key, title) in enumerate(STEPS, 1):
        step = Step(n, key, title, texts[key](ex))
        if render:
            step.image = _sheet(ex, step, images[key](ex, pages))
        ex.steps.append(step)
    return ex


def placements(page: Page) -> list[Placement]:
    return [p for p in page.meta.get("placements", ()) if isinstance(p, Placement)]


def areas(page: Page) -> list[tuple[str, Any]]:
    return list(page.meta.get("areas", ()))


def _origin(t: Template) -> str:
    try:
        return {"builtin": "built in", "installed": "installed", "file": "a template file",
                "registered": "registered"}[template_origin(t.name)]
    except Exception:  # loaded by path, not by name
        return "a template file"


def _sources(page: Page) -> list[str]:
    """What the tokens are drawn from: shape names and SVG file names, in first-use order."""
    out = []
    for pl in placements(page):
        tok = pl.token
        out.append(f"`{Path(tok.shape).name}`" if tok.is_svg else f"the `{tok.shape}` shape")
    return list(dict.fromkeys(out))


def _count(n: int, word: str, plural: str | None = None) -> str:
    return f"{n} {word if n == 1 else plural or word + 's'}"


def _listing(items: Sequence[str]) -> str:
    items = list(items)
    if len(items) <= 2:
        return " and ".join(items)
    return ", ".join(items[:-1]) + " and " + items[-1]


def _own_values(ex: Explainer) -> dict[str, Any]:
    return {k: v for k, v in ex.values.items() if k not in COMMON_NAMES}


def _inputs_text(ex: Explainer) -> str:
    t, own = ex.template, _own_values(ex)
    sources = _sources(ex.page)
    svg = any(pl.token.is_svg for pl in placements(ex.page))
    if len(sources) > 4:
        sources = [*sources[:3], f"{len(sources) - 3} more"]
    tokens = (f" The tokens are drawn from {_listing(sources)}" + (", SVG files read as vector art." if svg else
              "; a token can also be an SVG file.")) if sources else ""
    return (f"A template and its parameter values. `{t.name}` is {_origin(t)}: {t.description[:1].lower()}"
            f"{t.description[1:]}. It takes {_count(len(own), 'parameter')} of its own (here its defaults) and "
            f"the five every template has: `device`, `theme`, `name`, `copies` and `intro`. Text comes in as "
            f"parameter values.{tokens}")


def _mm(px: float, device: Device) -> str:
    return f"{px / device.mm(1):.0f}"


def _layout_text(ex: Explainer) -> str:
    d, page = ex.device, ex.page
    w, h = page_size(d, page.landscape)
    kinds = [label.split()[0] for label, _ in areas(page)]
    counted = [_count(kinds.count(k), k) for k in dict.fromkeys(kinds)]
    pls = placements(page)
    boxes = (f" The template works out {_listing(counted)}" if counted else
             " The template works out where everything goes")
    slots = f", and a slot for each of its {_count(len(pls), 'token')} (the thin boxes)" if pls else ""
    return (f"Everything is placed in device pixels, the unit pen strokes use: {w} × {h} px "
            f"({_mm(w, d)} × {_mm(h, d)} mm at {d.dpi} ppi on the {d.name}).{boxes}{slots}. "
            f"Then the background is drawn into a PDF page from those boxes; nothing on it can move.")


def _strokes_text(ex: Explainer) -> str:
    pls = placements(ex.page)
    total = len(ex.page.strokes)
    if not pls:
        return (f"Everything that should move is pen strokes: {_count(total, 'stroke')} on this page, "
                f"each a line of points with a pen width (one colour per stroke here).")
    pl = pls[0]
    tok, strokes = pl.token, pl.art.strokes
    points = sum(len(s.points) for s in strokes)
    if tok.is_svg:
        how = (f"the SVG `{Path(tok.shape).name}` is read into dark and light regions, which become outline "
               f"strokes and hatching ({tok.style})")
    else:
        how = f"its `{tok.shape}` shape becomes {'outline' if tok.style == 'outline' else tok.style} strokes"
    label = f" and its label “{tok.text}” is written in a single-line stroke font" if tok.text else ""
    return (f"Each token turns into pen strokes: {how}{label}. This one is {_count(len(strokes), 'stroke')} with "
            f"{points} points (one colour per stroke here; white ink shows light grey), written one after another so a single lasso picks the "
            f"token up as one piece. The page has {_count(len(pls), 'token')}, {_count(total, 'stroke')} in all.")


def _layers_text(ex: Explainer) -> str:
    page = ex.page
    names = [f"“{n}” ({_count(len(s), 'stroke')})" if s else f"“{n}” (empty)" for n, s in page.rm_layers()]
    hw = f" “{page.handwriting}” is empty: it's for the pen, so a lasso on a stroke layer never picks up " \
         f"handwriting." if page.handwriting else ""
    return (f"The strokes go onto named layers, bottom to top: {_listing(names)}. The PDF background sits "
            f"under all of them and can't be selected.{hw} On the tablet: pick a layer, lasso, drag.")


def _finished_text(ex: Explainer) -> str:
    d = ex.device
    note = "" if d.verified else (f" The {d.name} output is unverified: it hasn't been checked on a real "
                                  f"tablet yet.")
    return ("The page is written two ways. As an `.rmdoc`, a zip of the PDF background, one `.rm` file of v6 "
            "pen strokes per page and two small JSON files, the tablet opens it as a notebook and the strokes "
            "stay movable. As a plain PDF the strokes are printed onto the background, for any reader or a "
            f"printer.{note}")


# --------------------------------------------------------------------------- pictures

def _font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(str(font_path(SANS_SEMIBOLD if bold else SANS)), size)


class _Pages:
    """The page rendered at 1 device px per pixel: background only, and with the strokes printed."""

    def __init__(self, ex: Explainer):
        self.ex = ex
        self._cache: dict[bool, Image.Image] = {}

    def size(self) -> tuple[int, int]:
        return page_size(self.ex.device, self.ex.page.landscape)

    def render(self, strokes: bool) -> Image.Image:
        if strokes not in self._cache:
            page, doc = self.ex.page, self.ex.doc
            one = Page(draw=page.draw, layers=page.layers if strokes else [], landscape=page.landscape,
                       fonts=page.fonts)
            pdf = Document(doc.device, [one], fonts=doc.fonts, initial_font=doc.initial_font).render_pdf(
                print_strokes=strokes)
            self._cache[strokes] = _pdf_png(pdf, doc.device, self.size())
        return self._cache[strokes].copy()

    def blank(self) -> Image.Image:
        return Image.new("RGB", self.size(), PAPER)


def _pdf_png(pdf: bytes, device: Device, size: tuple[int, int]) -> Image.Image:
    try:
        import pypdfium2 as pdfium
    except ImportError:
        raise ValueError('the explainer\'s pictures need pypdfium2: pip install "rmstrokes[preview]"') from None
    doc = pdfium.PdfDocument(pdf)
    try:
        image = doc[0].render(scale=1 / device.pt_per_px).to_pil().convert("RGB")
    finally:
        doc.close()
    return image if image.size == size else image.resize(size)


def _faded(image: Image.Image, amount: float = 0.7) -> Image.Image:
    return Image.blend(image, Image.new("RGB", image.size, PAPER), amount)


def _draw_strokes(draw: ImageDraw.ImageDraw, strokes: Sequence[Stroke], *, scale: float = 1.0,
                  offset: tuple[float, float] = (0, 0), colors: Sequence[str] | None = None,
                  min_width: float = 1.0):
    """Strokes as round-capped polylines: in their pen colour, or one of `colors` each (white ink
    then shows as a light tint, so it can be seen on white)."""
    ox, oy = offset
    for i, s in enumerate(strokes):
        if not s.points:
            continue
        if s.color.name == "WHITE":
            color = WHITE_INK if colors else PAPER
        else:
            color = colors[i % len(colors)] if colors else STROKE_COLORS.get(s.color.name, INK)
        pts = [(x * scale + ox, y * scale + oy) for x, y in s.points]
        w = max(min_width, s.width * scale)
        if len(pts) > 1:
            draw.line(pts, fill=color, width=round(w), joint="curve")
        r = w / 2
        for x, y in (pts[0], pts[-1]):  # round caps
            draw.ellipse((x - r, y - r, x + r, y + r), fill=color)


def _dashed_rect(draw: ImageDraw.ImageDraw, box, color: str, width: int, dash: float):
    x0, y0, x1, y1 = box
    for (ax, ay), (bx, by) in (((x0, y0), (x1, y0)), ((x1, y0), (x1, y1)), ((x1, y1), (x0, y1)), ((x0, y1), (x0, y0))):
        length = max(abs(bx - ax), abs(by - ay))
        steps = max(1, int(length // (2 * dash)))
        for k in range(steps + 1):
            t0, t1 = 2 * k * dash / length if length else 0, min(1, (2 * k + 1) * dash / length) if length else 1
            if t0 >= 1:
                break
            draw.line((ax + (bx - ax) * t0, ay + (by - ay) * t0, ax + (bx - ax) * t1, ay + (by - ay) * t1),
                      fill=color, width=width)


def _wrap(text: str, f: ImageFont.FreeTypeFont, width: float) -> list[str]:
    lines = []
    for para in text.split("\n"):
        line = ""
        for word in para.split():
            trial = f"{line} {word}".strip()
            if line and f.getlength(trial) > width:
                lines.append(line)
                line = word
            else:
                line = trial
        lines.append(line)
    return lines


def _card(size: tuple[int, int], blocks: Sequence[tuple[str, Sequence[str]]]) -> Image.Image:
    """A text panel at page size: blocks of (heading, lines), scaled to the page."""
    w, h = size
    image = Image.new("RGB", size, PAPER)
    d = ImageDraw.Draw(image)
    unit = w / 34  # about 41 px on a portrait rm2 page
    head, body = _font(round(unit * 1.1), bold=True), _font(round(unit * 0.9))
    x, y, width = unit * 2, unit * 2, w - unit * 4
    for heading, lines in blocks:
        if heading:
            d.text((x, y), heading, font=head, fill=INK)
            y += unit * 1.8
        for line in lines:
            for part in _wrap(line, body, width):
                if y > h - unit * 2:
                    d.text((x, y), "…", font=body, fill=MUTED)
                    return image
                d.text((x, y), part, font=body, fill=INK if not line.startswith("  ") else MUTED)
                y += unit * 1.3
        y += unit * 1.2
    return image


Panel = tuple[str, str, Image.Image]  # (caption, note under it, picture)


def _inputs_image(ex: Explainer, pages: _Pages) -> tuple[list[Panel], str]:
    t, page = ex.template, ex.page
    own = _own_values(ex)
    params = []
    for k, v in own.items():
        shown = ", ".join(map(str, v)) if isinstance(v, (list, tuple)) else str(v)
        params.append(f"{k} = {shown}")
    common = [f"device = {ex.device.key}", f"theme = {ex.values['theme']}"]
    template_card = _card(pages.size(), [
        (f"template: {t.name}", [t.title, f"  {_origin(t)}", f"  {'landscape' if page.landscape else 'portrait'}"]),
        ("parameters", params or ["(none)"]),
        ("common", common),
    ])
    panels: list[Panel] = [("Template + values", "text in", template_card)]
    pls = placements(page)
    if pls:
        seen, arts = set(), []
        for pl in pls:
            key = pl.token.shape
            if key not in seen:
                seen.add(key)
                arts.append(pl)
        panels.append(("Token sources", ", ".join(_plain(s) for s in _sources(page)),
                       _sources_image(arts[:12], pages)))
    return panels, "arrow"


def _plain(md: str) -> str:
    return md.replace("`", "")


def _source_region(pl: Placement, device: Device):
    """(dark, light) regions of the token's source in its own px, corner at (0, 0)."""
    tok = pl.token
    w = device.mm(tok.size_mm)
    if tok.is_svg:
        art = load_art(Path(tok.shape), w, tok.svg_units)
        return art.dark, art.light
    h = device.mm(tok.height_mm) if tok.height_mm else None
    return None, shape_region(tok.shape, w, h)


def _fill_region(draw: ImageDraw.ImageDraw, region, scale: float, offset, fill: str, outline: str | None,
                 width: int = 2):
    if region is None or region.is_empty:
        return
    ox, oy = offset
    geoms = getattr(region, "geoms", [region])
    for g in geoms:
        if g.geom_type != "Polygon":
            continue
        ext = [(x * scale + ox, y * scale + oy) for x, y in g.exterior.coords]
        draw.polygon(ext, fill=fill, outline=outline, width=width if outline else 0)
        for hole in g.interiors:
            draw.polygon([(x * scale + ox, y * scale + oy) for x, y in hole.coords], fill=PAPER, outline=outline,
                         width=width if outline else 0)


def _fit(bounds, box) -> tuple[float, tuple[float, float]]:
    """Scale and offset that fit `bounds` (x0, y0, x1, y1) centred into `box` (x, y, w, h)."""
    x0, y0, x1, y1 = bounds
    bx, by, bw, bh = box
    k = min(bw / max(x1 - x0, 1e-6), bh / max(y1 - y0, 1e-6))
    return k, (bx + (bw - (x1 - x0) * k) / 2 - x0 * k, by + (bh - (y1 - y0) * k) / 2 - y0 * k)


def _sources_image(pls: Sequence[Placement], pages: _Pages) -> Image.Image:
    """Each distinct token source as read: SVG dark/light regions, or the primitive shape."""
    image = pages.blank()
    d = ImageDraw.Draw(image)
    w, h = image.size
    cols = 1 if len(pls) == 1 else 2 if len(pls) <= 4 else 3
    rows = -(-len(pls) // cols)
    m = w * 0.06
    cw, ch = (w - 2 * m) / cols, min((h - 2 * m) / rows, (w - 2 * m) / cols * 1.4)
    label = _font(round(w / 40))
    for i, pl in enumerate(pls):
        dark, light = _source_region(pl, pages.ex.device)
        regions = [r for r in (dark, light) if r is not None and not r.is_empty]
        if not regions:
            continue
        bx = [min(r.bounds[0] for r in regions), min(r.bounds[1] for r in regions),
              max(r.bounds[2] for r in regions), max(r.bounds[3] for r in regions)]
        x, y = m + (i % cols) * cw, m + (i // cols) * ch
        k, off = _fit(bx, (x + cw * 0.1, y + ch * 0.08, cw * 0.8, ch * 0.7))
        _fill_region(d, light, k, off, "#ecebe7" if dark is None else PAPER, INK, 2)
        _fill_region(d, dark, k, off, INK, None)
        name = Path(pl.token.shape).name if pl.token.is_svg else pl.token.shape
        d.text((x + cw / 2, y + ch * 0.86), name, font=label, fill=MUTED, anchor="mm")
    return image


def _layout_image(ex: Explainer, pages: _Pages) -> tuple[list[Panel], str]:
    page, d = ex.page, ex.device
    w, h = pages.size()
    wire = pages.blank()
    draw = ImageDraw.Draw(wire)
    lw = max(2, round(d.mm(0.35)))
    label = _font(round(d.mm(4)))
    for pl in placements(page):
        b = pl.box
        draw.rectangle((b.x, b.y, b.right, b.bottom), outline=LINE, width=max(1, lw // 2))
    for name, r in areas(page):
        _dashed_rect(draw, (r.x, r.y, r.right, r.bottom), ACCENT, lw, d.mm(1.2))
        if r.h < d.mm(12) and r.right + d.mm(2) + label.getlength(name) < w:  # a short box: beside it
            draw.text((r.right + d.mm(2), r.y + r.h / 2), name, font=label, fill=ACCENT, anchor="lm")
        else:
            draw.text((r.x + lw * 2, r.y + lw * 2), name, font=label, fill=ACCENT)
    if not areas(page) and not placements(page):  # no layout data: the stroke layers' extent
        for layer in page.layers:
            if layer.strokes:
                xs = [x for s in layer.strokes for x, _ in s.points]
                ys = [y for s in layer.strokes for _, y in s.points]
                _dashed_rect(draw, (min(xs), min(ys), max(xs), max(ys)), ACCENT, lw, d.mm(1.2))
                draw.text((min(xs) + lw * 2, min(ys) + lw * 2), layer.name, font=label, fill=ACCENT)
    dims = _font(round(d.mm(4)))
    draw.text((w / 2, h - d.mm(4)), f"{w} × {h} px  ·  {_mm(w, d)} × {_mm(h, d)} mm", font=dims, fill=MUTED,
              anchor="mm")
    bg = pages.render(strokes=False)
    return [("Boxes, in device px", f"{len(areas(page))} areas, {len(placements(page))} slots", wire),
            ("PDF background", "drawn with reportlab", bg)], "arrow"


def _strokes_image(ex: Explainer, pages: _Pages) -> tuple[list[Panel], str]:
    page, d = ex.page, ex.device
    pls = placements(page)
    w, h = pages.size()
    if not pls:
        image = pages.blank()
        _draw_strokes(ImageDraw.Draw(image), page.strokes, colors=HUES)
        return [("Pen strokes", _count(len(page.strokes), "stroke"), image)], "arrow"
    pl = pls[0]
    m = w * 0.08
    box = (m, h * 0.2, w - 2 * m, h * 0.55)

    source = pages.blank()
    dark, light = _source_region(pl, d)
    regions = [r for r in (dark, light) if r is not None and not r.is_empty]
    bounds = (min(r.bounds[0] for r in regions), min(r.bounds[1] for r in regions),
              max(r.bounds[2] for r in regions), max(r.bounds[3] for r in regions))
    k, off = _fit(bounds, box)
    sd = ImageDraw.Draw(source)
    _fill_region(sd, light, k, off, "#ecebe7" if dark is None else PAPER, INK, 3)
    _fill_region(sd, dark, k, off, INK, None)
    if pl.token.text:
        sd.text((w / 2, box[1] + box[3] + h * 0.08), f"label “{pl.token.text}”", font=_font(round(w / 28)),
                fill=MUTED, anchor="mm")
    name = Path(pl.token.shape).name if pl.token.is_svg else f"{pl.token.shape} shape"

    strokes = pages.blank()
    k, off = _fit((0, 0, pl.art.width, pl.art.height), box)
    _draw_strokes(ImageDraw.Draw(strokes), pl.art.strokes, scale=k, offset=off, colors=HUES, min_width=3)
    n_points = sum(len(s.points) for s in pl.art.strokes)

    placed = _faded(pages.render(strokes=True), 0.6)
    pd = ImageDraw.Draw(placed)
    _draw_strokes(pd, pl.strokes())
    b = pl.box
    pd.rectangle((b.x - 6, b.y - 6, b.right + 6, b.bottom + 6), outline=ACCENT, width=max(3, round(d.mm(0.4))))
    return [(f"Source: {name}", "regions, before strokes", source),
            ("Pen strokes", f"{_count(len(pl.art.strokes), 'stroke')}, {n_points} points", strokes),
            ("In its slot", f"{_count(len(pls), 'token')} on the page", placed)], "arrow"


def _layers_image(ex: Explainer, pages: _Pages) -> tuple[list[Panel], str]:
    page = ex.page
    panels: list[Panel] = [("PDF background", "fixed", pages.render(strokes=False))]
    for name, strokes in page.rm_layers():
        image = pages.blank()
        draw = ImageDraw.Draw(image)
        if strokes:
            _draw_strokes(draw, strokes)
            note = _count(len(strokes), "stroke")
        else:
            w, h = image.size
            draw.text((w / 2, h / 2), "empty: for the pen", font=_font(round(w / 22)), fill=MUTED, anchor="mm")
            note = "handwriting" if name == page.handwriting else "empty"
        panels.append((f"Layer “{name}”", note, image))
    return panels, "plus"


def _finished_image(ex: Explainer, pages: _Pages) -> tuple[list[Panel], str]:
    doc = ex.doc
    ids = doc.ids(f"explain-{ex.stem}", ex.template.seed_namespace)
    pdf = doc.render_pdf()
    rms = doc.rm_pages(ids.author)
    kib = lambda n: f"{n / 1024:.1f} KiB"  # noqa: E731
    lines = [f"{ids.doc[:8]}….content", "  JSON: page list, orientation", f"{ids.doc[:8]}….metadata",
             f"  JSON: name “{doc.title}”", f"{ids.doc[:8]}….pdf", f"  the background, {kib(len(pdf))}"]
    for pid, rm, page in zip(ids.pages, rms, doc.pages):
        lines += [f"{ids.doc[:8]}…/{pid[:8]}….rm", f"  v6 pen strokes, {kib(len(rm))}"]
        lines += [f"  · {n}: {_count(len(s), 'stroke')}" for n, s in page.rm_layers()]
    card = _card(pages.size(), [(".rmdoc: a zip", lines)])
    return [("On the tablet: .rmdoc", "strokes movable", card),
            ("PDF export", "strokes printed", pages.render(strokes=True))], "none"


def _sheet(ex: Explainer, step: Step, made: tuple[list[Panel], str]) -> Image.Image:
    """The step's panels side by side, a caption over each, a header line on top."""
    panels, sep = made
    w0, h0 = panels[0][2].size
    n = len(panels)
    target_h = PANEL_H if n <= 3 else round(PANEL_H * max(0.5, 3 / n))
    k = min(target_h / h0, PANEL_MAX_W / w0)
    pw, ph = round(w0 * k), round(h0 * k)
    head_f, cap_f, note_f = _font(30, bold=True), _font(24, bold=True), _font(20)
    top = PAD + 48
    cap_h = 64
    width = PAD * 2 + n * pw + (n - 1) * GAP
    height = top + cap_h + ph + PAD
    sheet = Image.new("RGB", (width, height), SHEET)
    d = ImageDraw.Draw(sheet)
    d.text((PAD, PAD), f"{step.n}. {step.title}", font=head_f, fill=INK)
    where = f"{ex.template.title or ex.template.name} · {ex.device.name}"
    x_end = width - PAD
    if not ex.device.verified:
        warn = " · unverified on a real tablet"
        d.text((x_end, PAD + 6), warn, font=note_f, fill=WARN, anchor="ra")
        x_end -= d.textlength(warn, font=note_f)
    d.text((x_end, PAD + 6), where, font=note_f, fill=MUTED, anchor="ra")
    for i, (caption, note, image) in enumerate(panels):
        x = PAD + i * (pw + GAP)
        d.text((x, top), caption, font=cap_f, fill=INK)
        d.text((x, top + 30), note, font=note_f, fill=MUTED)
        y = top + cap_h
        sheet.paste(image.resize((pw, ph), Image.LANCZOS), (x, y))
        d.rectangle((x - 1, y - 1, x + pw, y + ph), outline=LINE, width=1)
        if i < n - 1 and sep != "none":
            cx, cy = x + pw + GAP / 2, y + ph / 2
            if sep == "arrow":
                d.line((cx - 18, cy, cx + 14, cy), fill=MUTED, width=4)
                d.polygon([(cx + 20, cy), (cx + 6, cy - 10), (cx + 6, cy + 10)], fill=MUTED)
            else:
                d.line((cx - 14, cy, cx + 14, cy), fill=MUTED, width=4)
                d.line((cx, cy - 14, cx, cy + 14), fill=MUTED, width=4)
    return sheet


# --------------------------------------------------------------------------- output

def write_explainers(explainers: Sequence[Explainer], out: Path, *, documents: bool = True) -> list[Path]:
    """Each step's PNG into `out` (<template>-<device>-<n>-<step>.png), and with `documents` the
    page as .rmdoc and .pdf (<template>-<device>.rmdoc/.pdf)."""
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    written = []
    for ex in explainers:
        for step in ex.steps:
            if step.image is not None:
                path = out / step.file_name(ex.stem)
                # 256 colours: the same picture at under half the size (flat fills, little gradient)
                step.image.quantize(256, Image.Quantize.MEDIANCUT, dither=Image.Dither.NONE).save(path, optimize=True)
                written.append(path)
        if documents:
            written.append(ex.doc.write(out / f"{ex.stem}.rmdoc", "rmdoc", seed=f"explain-{ex.stem}",
                                        namespace=ex.template.seed_namespace).path)
            written.append(ex.doc.write(out / f"{ex.stem}.pdf", "pdf").path)
    return written


def markdown(explainers: Sequence[Explainer], image_dir: str, command: str) -> str:
    """The explainer as a markdown page; images under `image_dir` (relative to the page)."""
    parts = [f"# {TITLE}\n\n<!-- Generated by `{command}`: edit the text in src/rmstrokes/explain.py, "
             f"not here. -->\n\n{INTRO}\n\nTo see the steps for any template: "
             f"`rmstrokes explain TEMPLATE [--device D] -o DIR` (a name or a `.toml`/`.py` file).\n"]
    for ex in explainers:
        parts.append(f"## {ex.heading}\n")
        if not ex.device.verified:
            parts.append(f"**Unverified:** the {ex.device.name} output hasn't been checked on a real tablet.\n")
        for step in ex.steps:
            src = f"{image_dir.rstrip('/')}/{step.file_name(ex.stem)}" if image_dir else step.file_name(ex.stem)
            parts.append(f"### {step.n}. {step.title}\n\n![{step.title}: {ex.template.name}, {ex.device.key}]"
                         f"({src})\n\n{step.text}\n")
    return "\n".join(parts)


def html_text(md: str) -> str:
    """The steps' markdown (`code`, “quotes”) as HTML."""
    return re.sub(r"`([^`]+)`", r"<code>\1</code>", html.escape(md, quote=False))
