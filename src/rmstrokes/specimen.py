"""The design system's specimen: every token of a theme printed on the device it is for.

    rmstrokes specimen -o out/            # rm2 in "default", pro in "color": rmdoc + PDF + PNG each
    rmstrokes specimen --device move --theme color -o out/

Type roles at their sizes, the grey ramp and what each grey may be used for, the Paper Pro
palette (with the grey an rM2 turns each colour into), line weights, a pattern, ruled lines with
a knocked-out label and two movable tokens whose name tags sit over the lines (one with a white
knock-out, one without), and the spacing steps. The tokens are real pen strokes on a layer, so on
the tablet they can be lassoed and moved over the lines.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Callable

from rmscene import scene_items as si

from .design import GREYS, PRO_ACCENTS, ROLES, Style, contrast, get_style, grey_uses, luminance
from .devices import Device, get_device
from .fields import FieldStyle, WriteIn, draw_write_in
from .geometry import Rect, page_size
from .layers import Document, Layer, Page
from .pdf import Painter
from .strokefont import text_strokes
from .tokens import NameTag, Token, token_art
from .vectorize import Stroke, hatch

# What each device's specimen shows unless asked otherwise: the rM2 in greys, the Pro in colour.
DEFAULT_RUNS = (("rm2", "default"), ("pro", "color"))
TOKEN_LAYER = "Tokens"

SAMPLES = {
    "title": "Sample page, Saturday",
    "heading": "Word bank, page 4",
    "label": "Label  Il1 O0 rn m",
    "body": "Lasso a token and drag it; its name tag moves with it.",
    "value": "Ana, 12 May",
    "italic": "Turn the page to begin.",
    "caps": "Summary",
    "caption": "Start here",
    "field": "Name",
    "small": "Small print 12  0123456789  the smallest size",
    "numeric": "  7   12  140  1250",
}


def font_label(name: str) -> str:
    """'AtkinsonHyperlegibleNext-SemiBold' -> 'Atkinson Hyperlegible Next SemiBold'."""
    family, _, weight = name.partition("-")
    family = re.sub(r"(?<=[a-z0-9])(?=[A-Z])|(?<=[A-Z])(?=[A-Z][a-z])|(?<=[a-z])(?=[0-9])", " ", family)
    return f"{family} {weight}".strip()


@dataclass
class Block:
    """A piece of the specimen: its height in px, its background and its strokes at a given top."""

    height: float
    draw: Callable[[Painter, float], None]
    strokes: Callable[[float], list[Stroke]] = lambda y: []
    keep_with_next: bool = False


class Specimen:
    def __init__(self, style: Style):
        self.s = style
        self.dev = style.device
        self.W, self.H = page_size(self.dev)
        self.margin = style.margin()
        self.x0 = self.margin
        self.cw = self.W - 2 * self.margin
        self.mm = style.mm

    # ------------------------------------------------------------------ helpers

    def text(self, p, s, x, y, role, **kw):
        self.s.draw_text(p, s, x, y, role, **kw)

    def wrap(self, text: str, role: str, width: float | None = None) -> list[str]:
        """`text` broken into lines that fit `width` (default: the content width) in `role`."""
        width = self.cw if width is None else width
        lines, line = [], ""
        for word in text.split(" "):
            trial = f"{line} {word}" if line else word
            if line and self.s.text_width(trial, role) > width:
                lines.append(line)
                line = word
            else:
                line = trial
        return [*lines, line] if line else lines

    def paragraph(self, p, text: str, x: float, y: float, role: str, **kw) -> float:
        """Wrapped text, first baseline at y; returns the y after the last line."""
        for line in self.wrap(text, role):
            self.text(p, line, x, y, role, **kw)
            y += self.line_h(role)
        return y

    def line_h(self, role, k=1.0) -> float:
        t = self.s.type(role)
        return self.s.size(role) * t.leading * k

    # ------------------------------------------------------------------ blocks

    def header(self) -> list[Block]:
        s, mm = self.s, self.mm
        verified = "" if self.dev.verified else " (unverified on this device)"
        sub = f"Theme {s.name} on the {self.dev.name}{verified}"
        h = self.line_h("title") + self.line_h("italic") * len(self.wrap(sub, "italic")) + mm(4)

        def draw(p, y):
            self.text(p, "Design system", self.x0, y + s.size("title") * 0.9, "title")
            self.paragraph(p, sub, self.x0, y + self.line_h("title") + s.size("italic"), "italic")
            p.line(self.x0, y + h - mm(1.5), self.x0 + self.cw, y + h - mm(1.5), s.line("rule"), s.color("ink"))
        return [Block(h, draw)]

    def section(self, title: str, note: str = "") -> Block:
        s, mm = self.s, self.mm
        h = mm(4) + self.line_h("heading") + self.line_h("small") * len(self.wrap(note, "small")) + mm(1)

        def draw(p, y):
            base = y + mm(4) + s.size("heading") * 0.9
            self.text(p, title, self.x0, base, "heading")
            self.paragraph(p, note, self.x0, base + self.line_h("small"), "small")
        return Block(h, draw, keep_with_next=True)

    def type_rows(self) -> list[Block]:
        s, mm = self.s, self.mm
        out = []
        for role in ROLES:
            t = s.type(role)
            extra = []
            if t.caps:
                extra.append("caps")
            if t.tracking:
                extra.append(f"+{t.tracking * 100:g}% tracking")
            meta = (f"{role}  {t.size_mm:g} mm / {t.size_pt:.1f} pt  {font_label(t.font)}  {t.color}"
                    + (f"  {', '.join(extra)}" if extra else ""))
            sample = SAMPLES[role]
            meta_h = self.line_h("small") * len(self.wrap(meta, "small"))
            if role == "field":
                body_h = mm(9)
            else:
                body_h = s.size(role) * 1.25
            h = meta_h + body_h + mm(2.5)

            def draw(p, y, role=role, meta=meta, sample=sample, meta_h=meta_h, body_h=body_h):
                self.paragraph(p, meta, self.x0, y + s.size("small"), "small")
                top = y + meta_h
                if role == "field":
                    w = min(self.cw, mm(80))
                    draw_write_in(p, WriteIn(sample), Rect(self.x0, top, w, body_h), FieldStyle.from_style(s))
                    return
                size = s.size(role)
                fit = min(1.0, self.cw / max(s.text_width(sample, role), 1e-6))
                self.text(p, sample, self.x0, top + size * 0.95, role, size=size * fit)
            out.append(Block(h, draw))
        return out

    def grey_ramp(self) -> list[Block]:
        s, mm = self.s, self.mm
        names = list(GREYS)
        per_row = 10 if self.cw >= mm(120) else 5
        gap = mm(1.5)
        sw = (self.cw - (per_row - 1) * gap) / per_row
        sh = mm(10)
        label_h = 3 * self.line_h("small")
        rows = [names[i:i + per_row] for i in range(0, len(names), per_row)]
        blocks = []
        for row in rows:
            def draw(p, y, row=row):
                for i, name in enumerate(row):
                    hexv = GREYS[name]
                    x = self.x0 + i * (sw + gap)
                    p.rect(Rect(x, y, sw, sh), fill=hexv, stroke=s.color("rule") if hexv == "#FFFFFF" else None,
                           width=s.line("hairline"))
                    ty = y + sh + s.size("small") * 1.2
                    self.text(p, name.replace("grey-", "") + "% ink", x, ty, "small", color="ink")
                    self.text(p, hexv, x, ty + self.line_h("small"), "small")
                    # The strongest use: a text grey also does for lines and guides.
                    uses = grey_uses(hexv)
                    self.text(p, f"{uses[0]}{' +' if len(uses) > 1 else ''}" if uses else
                              ("paper" if hexv == "#FFFFFF" else "avoid"), x,
                              ty + 2 * self.line_h("small"), "small")
            blocks.append(Block(sh + label_h + mm(2), draw))
        return blocks

    def grey_tokens(self) -> list[Block]:
        """The semantic greys in use: text in each text grey, lines in each line grey, ink on each fill."""
        s, mm = self.s, self.mm
        col = (self.cw - 2 * mm(3)) / 3
        out = []

        def text_row(p, y):
            for i, tok in enumerate(("ink", "ink-2", "muted")):
                x = self.x0 + i * (col + mm(3))
                self.text(p, f"{tok}: Label 0123", x, y + s.size("label"), "label", color=tok)
                self.text(p, f"{s.color(tok)}  {contrast(s.color(tok)):.1f}:1", x,
                          y + s.size("label") + self.line_h("small"), "small")
        out.append(Block(s.size("label") + self.line_h("small") * 1.6, text_row))

        def line_row(p, y):
            mid = y + mm(2)
            for i, (tok, weight) in enumerate((("rule", "hairline"), ("rule", "rule"), ("guide", "line"))):
                x = self.x0 + i * (col + mm(3))
                p.line(x, mid, x + col, mid, s.line(weight), s.color(tok))
                ty = mid + mm(1) + s.size("small")
                self.text(p, f"{tok} at {weight}", x, ty, "small")
                self.text(p, f"{getattr(s.lines, weight):g} mm  {contrast(s.color(tok)):.1f}:1", x,
                          ty + self.line_h("small"), "small")
        out.append(Block(mm(4) + self.line_h("small") * 2.4, line_row))

        def fill_row(p, y):
            bh = mm(9)
            for i, tok in enumerate(("surface-strong", "surface", "surface-faint")):
                x = self.x0 + i * (col + mm(3))
                p.rect(Rect(x, y, col, bh), fill=s.color(tok), radius=mm(1))
                self.text(p, tok, x + mm(2), y + bh / 2 + s.size("label") * 0.35, "label")
                ty = y + bh + s.size("small") * 1.2
                self.text(p, s.color(tok), x, ty, "small")
                self.text(p, f"ink on it {contrast('#000000', s.color(tok)):.1f}:1", x, ty + self.line_h("small"),
                          "small")
        out.append(Block(mm(9) + self.line_h("small") * 2.6, fill_row))
        return out

    def colours(self) -> list[Block]:
        s, mm = self.s, self.mm
        cols = 3 if self.cw >= mm(120) else 2
        gap = mm(3)
        cw = (self.cw - (cols - 1) * gap) / cols
        ch = mm(16)
        label_h = self.line_h("small") * 1.3
        entries = [(name, ink, tint, f"accent-{i}") for i, (name, ink, tint) in enumerate(PRO_ACCENTS, 1)]
        blocks = []
        for r in range(0, len(entries), cols):
            row = entries[r:r + cols]

            def draw(p, y, row=row):
                for i, (name, ink, tint, token) in enumerate(row):
                    x = self.x0 + i * (cw + gap)
                    box = Rect(x, y, cw, ch)
                    p.rect(box, fill=tint, radius=mm(1))
                    p.rect(Rect(x, y, mm(3), ch), fill=ink)
                    pair = {"accent-1": "  pair-a", "accent-2": "  pair-b"}.get(token, "")
                    self.text(p, f"{token}  {name}{pair}", x + mm(5), y + mm(5), "label")
                    self.text(p, f"ink {ink}  tint {tint}", x + mm(5), y + mm(5) + self.line_h("small"), "small",
                              color="ink-2")
                    # What an rM2 makes of it: the grey of the same lightness, ink and tint.
                    for j, c in enumerate((ink, tint)):
                        g = round(luminance(c) ** (1 / 2.2) * 255)
                        grey = f"#{g:02X}{g:02X}{g:02X}"
                        p.rect(Rect(box.right - mm(2) - (2 - j) * mm(4.5), y + ch - mm(5.5), mm(4), mm(4)),
                               fill=grey, stroke=s.color("rule"), width=s.line("hairline"))
                    self.text(p, f"{contrast(ink):.1f}:1", x + mm(5), y + ch - mm(2), "small", color="ink-2")
            blocks.append(Block(ch + gap, draw))
        text = "Small squares: the grey of the same lightness (how a greyscale panel shows it)."
        note = Block(label_h * len(self.wrap(text, "small")),
                     lambda p, y: self.paragraph(p, text, self.x0, y + s.size("small"), "small"))
        return blocks + [note]

    def line_weights(self) -> list[Block]:
        s, mm = self.s, self.mm
        out = []
        label_w = min(mm(62), self.cw * 0.45)
        for name in ("hairline", "rule", "line", "strong", "heavy"):
            v = getattr(s.lines, name)
            px = s.line(name)

            def draw(p, y, name=name, v=v, px=px):
                mid = y + mm(2.5)
                self.text(p, f"{name}  {v:g} mm = {px:.1f} px", self.x0, mid + s.size("small") * 0.35, "small",
                          color="ink")
                p.line(self.x0 + label_w, mid, self.x0 + self.cw, mid, px, s.color("ink"))
            out.append(Block(mm(5), draw))

        def dotted(p, y):
            mid = y + mm(2.5)
            self.text(p, f"dotted  {s.lines.dot:g} mm, gap {s.lines.dot_gap:g}",
                      self.x0, mid + s.size("small") * 0.35, "small", color="ink")
            c = p.c
            c.saveState()
            w = s.line("dot")
            p.dash("dotted", w, mm(s.lines.dot_gap))
            p.line(self.x0 + label_w, mid, self.x0 + self.cw, mid, w, s.color("guide"))
            c.restoreState()
        out.append(Block(mm(5), dotted))

        def pattern(p, y):
            box = Rect(self.x0 + label_w, y + mm(1), self.cw - label_w, mm(8))
            self.text(p, "pattern: only when a fill can't", self.x0, y + mm(4), "small", color="ink")
            self.text(p, f"{s.lines.hatch:g} mm at {s.lines.hatch_pitch:g} mm, 45 degrees", self.x0,
                      y + mm(4) + self.line_h("small"), "small")
            p.rect(box, stroke=s.color("rule"), width=s.line("hairline"))
            from shapely.geometry import box as sbox
            for chain in hatch(sbox(box.x, box.y, box.right, box.bottom), mm(s.lines.hatch_pitch), 45):
                p.polyline(chain, s.line("hatch"), s.color("ink"))
        out.append(Block(mm(10), pattern))
        return out

    def lined(self) -> list[Block]:
        """Ruled lines with a knocked-out caption and two tokens whose tags sit on the lines."""
        s, mm = self.s, self.mm
        h = mm(44)
        pitch = mm(s.spacing.write_pitch)
        size = 9.0
        tag_w = 24.0
        tokens = []
        for knockout, pair in ((True, "pair-a"), (False, "pair-b")):
            tok = Token("circle", size_mm=size, style="outline", pen_mm=0.4, number=7 if knockout else 9,
                        name_tag=NameTag(width_mm=tag_w, height_mm=7.5, knockout=knockout))
            tokens.append((knockout, pair, token_art(tok, self.dev)))

        def centres(y):
            return [(self.x0 + self.cw * f, y + mm(10) + tokens[0][2].height / 2) for f in (0.27, 0.73)]

        def draw(p, y):
            yy = y + pitch
            while yy <= y + h - 1e-6:
                p.line(self.x0, yy, self.x0 + self.cw, yy, s.line("hairline"), s.color("rule"))
                yy += pitch
            s.knockout_text(p, "Notes", self.x0, y + pitch + s.size("caption") * 0.35, "caption")
            for (knockout, _, art), (cx, cy) in zip(tokens, centres(y)):
                label = "tag with white knock-out" if knockout else "tag without knock-out"
                s.knockout_text(p, label, cx, cy + art.height / 2 + mm(5), "small", align="center")

        def strokes(y):
            out = []
            for (knockout, pair, art), (cx, cy) in zip(tokens, centres(y)):
                pen = s.pen(pair)
                placed = art.placed(cx, cy)
                tag = art.tag.moved(cx - art.width / 2, cy - art.height / 2)
                placed += text_strokes("ANA", tag.center[0], tag.center[1] + mm(0.3), tag.h * 0.45, mm(0.35))
                out += [st if st.color == si.PenColor.WHITE else replace(st, color=pen) for st in placed]
            return out
        return [Block(h + mm(2), draw, strokes)]

    def spacing(self) -> list[Block]:
        s, mm = self.s, self.mm
        sp = s.spacing

        note = (f"margin {sp.margin:g} mm on the {self.dev.name}   gutter {sp.gutter:g} mm   "
                f"toolbar gap {sp.toolbar:g} mm   writing lines {sp.write_pitch:g} mm apart")

        def draw(p, y):
            x = self.x0
            for step in sp.steps:
                p.rect(Rect(x, y, mm(step), mm(3)), fill=s.color("ink"))
                self.text(p, f"{step:g}", x, y + mm(3) + s.size("small") * 1.2, "small", color="ink")
                x += mm(step) + mm(4)
            self.paragraph(p, note, self.x0, y + mm(3) + s.size("small") * 1.2 + self.line_h("small") * 1.3,
                           "small")
        return [Block(mm(3) + self.line_h("small") * (1.8 + len(self.wrap(note, "small"))), draw)]

    def sections(self) -> list[Block]:
        s = self.s
        colour_note = ("Used by this theme." if s.color_ok
                       else "The color theme's palette, for the Paper Pro; this theme uses greys instead.")
        return [
            *self.header(),
            self.section("Type", "Sizes are the font size (em) in mm; 1 pt = 0.353 mm."), *self.type_rows(),
            self.section("Greys", "Multiples of 0x11: the rM2 shows 16 levels. "
                                  "Uses from contrast on white: text 7:1, line 4.5:1, guide 3:1."),
            *self.grey_ramp(), *self.grey_tokens(),
            self.section("Paper Pro colour", colour_note), *self.colours(),
            self.section("Lines", f"1 px = {25.4 / self.dev.dpi:.3f} mm on this device; nothing under "
                                  f"{s.lines.hairline:g} mm."),
            *self.line_weights(),
            self.section("Over ruled lines", "Labels and tags on lines get a white knock-out. "
                                             "The tokens are pen strokes: lasso and move them."),
            *self.lined(),
            self.section("Spacing", "A 1 mm grid; gaps come from these steps (mm)."), *self.spacing(),
        ]

    # ------------------------------------------------------------------ pages

    def footer(self, p, n: int, total: int):
        s = self.s
        y = self.H - self.margin * 0.45
        note = "" if self.dev.verified else "  unverified on device"
        self.text(p, f"rmstrokes specimen  {s.name}  {self.dev.key}{note}", self.x0, y, "small")
        self.text(p, f"{n} / {total}", self.x0 + self.cw, y, "small", align="right")

    def pages(self) -> list[Page]:
        bottom = self.H - self.margin - self.mm(4)
        pages: list[list[tuple[Block, float]]] = [[]]
        y = self.margin
        blocks = self.sections()
        for i, b in enumerate(blocks):
            need = b.height + (blocks[i + 1].height if b.keep_with_next and i + 1 < len(blocks) else 0)
            if y + need > bottom and pages[-1]:
                pages.append([])
                y = self.margin
            pages[-1].append((b, y))
            y += b.height
        out = []
        for n, placed in enumerate(pages, 1):
            def draw(p, placed=placed, n=n):
                for b, top in placed:
                    b.draw(p, top)
                self.footer(p, n, len(pages))
            strokes = [st for b, top in placed for st in b.strokes(top)]
            out.append(Page(draw=draw, layers=[Layer(TOKEN_LAYER, strokes)] if strokes else [],
                            handwriting="Notes", fonts=self.s.fonts, kind="specimen"))
        return out


def specimen_document(device: Device | str, theme: str = "default") -> Document:
    style = get_style(theme, device)
    dev = style.device
    return Document(dev, Specimen(style).pages(), title=f"Design system {theme} {dev.key}",
                    creator="rmstrokes specimen", subject=f"{dev.name}, theme {theme}",
                    fonts=style.fonts, initial_font=style.font("body"))


def write_png(doc: Document, out: Path, page: int = 0) -> Path:
    """Page `page` of the PDF export (strokes printed) as a PNG, 1 device px per pixel."""
    try:
        import pypdfium2 as pdfium
    except ImportError:
        raise ValueError("PNG previews need pypdfium2 (pip install pypdfium2), or pass --no-png") from None
    pdf = pdfium.PdfDocument(doc.render_pdf(print_strokes=True))
    try:
        image = pdf[page].render(scale=1 / doc.device.pt_per_px).to_pil().convert("RGB")
        size = page_size(doc.device, doc.pages[page].landscape)
        if image.size != size:  # pdfium rounds the scaled page size up by a pixel at times
            image = image.resize(size)
        image.save(out, optimize=True)
    finally:
        pdf.close()
    return out


def write_specimens(out_dir: Path, runs, *, png: bool = True) -> list[Path]:
    """Write `specimen-<device>-<theme>.rmdoc` and `.pdf` (and a `.png` per page) for each
    (device, theme) in `runs`."""
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    written = []
    for device, theme in runs:
        dev = get_device(device)
        doc = specimen_document(dev, theme)
        stem = out_dir / f"specimen-{dev.key}-{theme}"
        written.append(doc.write(stem.with_suffix(".rmdoc"), namespace="rmstrokes-specimen",
                                 seed=f"specimen-{dev.key}-{theme}").path)
        written.append(doc.write(stem.with_suffix(".pdf")).path)
        if png:
            for i in range(len(doc.pages)):
                suffix = "" if len(doc.pages) == 1 else f"-{i + 1}"
                written.append(write_png(doc, stem.with_name(f"{stem.name}{suffix}.png"), i))
    return written

