"""Design tokens: the type, colour, line and spacing rules every template draws with.

A ``Style`` is one theme resolved for one device: fonts and sizes per text role, the palette
(semantic colour tokens), line weights and spacing, all in mm and converted to device px on
request. Two themes:

  default   the system: Atkinson Hyperlegible Next for everything you read, Source Serif 4 for
            titles (when a font package provides it), a greyscale palette tuned for the reMarkable 2
  color     the same type and greys plus a soft Paper Pro colour palette (accents, a contrasting pair)

Another package can add a theme of its own with ``register_theme``.

    style = get_style("default", device)
    p.text("Notes", x, y, style.font("caption"), style.size("caption"), style.color("muted"))
    style.draw_text(p, "Notes", x, y, "caption")         # the same, with the role's tracking and case

Templates pick their style through their theme (templates.Template.style_for); a Context always
carries one. The reasoning behind every value is in docs/design-system.md; `rmstrokes specimen`
prints them all.
"""
from __future__ import annotations

from dataclasses import dataclass, field, replace
from functools import cache
from typing import Callable, Mapping

from rmscene import scene_items as si

from . import fonts
from .devices import Device, get_device
from .geometry import Rect, page_size

# --------------------------------------------------------------------------- fonts

# Bundled with the engine (rmstrokes/fonts/).
SANS = "AtkinsonHyperlegibleNext-Regular"
SANS_ITALIC = "AtkinsonHyperlegibleNext-Italic"
SANS_SEMIBOLD = "AtkinsonHyperlegibleNext-SemiBold"
# Preferred where a font package provides them (fonts.py, entry point group rmstrokes.fonts); without
# one, a role set in them falls back to the bundled face in FALLBACK, so the engine alone still renders.
SANS_MEDIUM = "AtkinsonHyperlegibleNext-Medium"
DISPLAY = "SourceSerif4Subhead-Semibold"
MONO = "IBMPlexMono-Medium"  # tabular figures only (columns of numbers)
# Regular is too thin at the 7 pt floor, so small print goes up to SemiBold; Atkinson's figures are proportional.
FALLBACK = {SANS_MEDIUM: SANS_SEMIBOLD, DISPLAY: SANS_SEMIBOLD, MONO: SANS}

# The design themes, built in first; register_theme adds to it.
THEMES: list[str] = ["default", "color"]
MM_PER_PT = 25.4 / 72

# Text roles, largest first. Sizes are the em in mm (the font size), not the cap height.
ROLES = ("title", "heading", "label", "body", "value", "italic", "caps", "caption", "field", "small",
         "numeric")


@dataclass(frozen=True)
class TextStyle:
    font: str
    size_mm: float
    color: str = "ink"     # a palette token
    tracking: float = 0.0  # extra space between characters, in em (caps want a little)
    caps: bool = False     # set in capitals
    leading: float = 1.3   # line height / size, for wrapped text

    @property
    def size_pt(self) -> float:
        return self.size_mm / MM_PER_PT


SYSTEM_TEXT: dict[str, TextStyle] = {
    "title": TextStyle(DISPLAY, 6.4, leading=1.15),         # 18 pt: page titles
    "heading": TextStyle(SANS_SEMIBOLD, 4.2, leading=1.2),  # 12 pt: section headings
    "label": TextStyle(SANS, 3.2),                          # 9 pt: names on the page, axis labels
    "body": TextStyle(SANS, 3.2, leading=1.4),              # 9 pt: instructions, running text
    "value": TextStyle(SANS, 3.6),                          # 10 pt: pre-filled values in write-ins
    "italic": TextStyle(SANS_ITALIC, 3.2, "muted"),         # hints, subtitles
    "caps": TextStyle(SANS_SEMIBOLD, 2.8, tracking=0.08, caps=True),  # 8 pt: section and group labels
    "caption": TextStyle(SANS_SEMIBOLD, 3.0, "ink-2"),     # names an area ("Start here")
    "field": TextStyle(SANS, 2.8, "muted"),                 # 8 pt: the label of a handwriting field
    "small": TextStyle(SANS_MEDIUM, 2.5, "muted"),          # 7 pt: the floor; notes, legends
    "numeric": TextStyle(MONO, 3.2),                        # tabular numbers that must line up
}

# The Move's page is 92 mm wide and held closer: big type comes down, small type never does.
DEVICE_TYPE_SCALE: dict[str, dict[str, float]] = {
    "move": {"title": 0.85, "heading": 0.9, "value": 0.92},
}

# --------------------------------------------------------------------------- colour

# The greyscale ramp. Every step is a multiple of 0x11: the rM2 panel shows 16 grey levels, so a
# grey between two levels gets dithered or rounded, and two greys one level apart are the closest
# that still look different. Named by how much ink they carry.
GREYS: dict[str, str] = {
    "grey-100": "#000000",
    "grey-80": "#333333",
    "grey-67": "#555555",
    "grey-60": "#666666",
    "grey-47": "#888888",
    "grey-33": "#AAAAAA",
    "grey-20": "#CCCCCC",
    "grey-13": "#DDDDDD",
    "grey-7": "#EEEEEE",
    "grey-0": "#FFFFFF",
}

# Paper Pro accents: (ink, tint). Ink is for lines, marks and large text (L* 39-49, moderate chroma:
# the Gallery 3 panel renders strong saturated darks muddy and dithered); tint is for fills
# (L* 86-90: lighter tints wash out to paper, the newsprint effect). Picked so every pair differs by
# CIE76 dE >= 20 (inks) and >= 13 (tints); tests/test_design.py checks it.
PRO_ACCENTS: tuple[tuple[str, str, str], ...] = (
    ("blue", "#2D5F9E", "#C6DCF3"),
    ("red", "#B5473A", "#F2CFC8"),
    ("green", "#3E7B45", "#D5E8C4"),
    ("amber", "#9A6B12", "#F1DFB4"),
    ("violet", "#6B4F96", "#E8D3EC"),
    ("teal", "#1F7470", "#C2E6E6"),
)

# Contrast floors against white paper (WCAG 2 ratio). E-ink paper is a light grey, not white, and
# the panel has no backlight, so we ask for more than a screen would: AAA for text.
MIN_CONTRAST = {"text": 7.0, "line": 4.5, "guide": 3.0}
# Fills sit behind ink text, so they must stay light enough to keep the text at the text floor.
MAX_FILL_INK = "#CCCCCC"

SYSTEM_GREY_TOKENS: dict[str, str] = {
    "ink": GREYS["grey-100"],           # text, outlines, everything that matters
    "ink-2": GREYS["grey-80"],          # secondary text, captions
    "muted": GREYS["grey-67"],          # the lightest text: field labels, hints, small print
    "rule": GREYS["grey-60"],           # thin lines (< 0.4 mm): writing lines, grids, frames
    "guide": GREYS["grey-47"],          # lines >= 0.35 mm only: dotted outlines, guides
    "surface-strong": GREYS["grey-20"],  # the darkest fill text may sit on
    "surface": GREYS["grey-13"],        # bands, shaded areas
    "surface-faint": GREYS["grey-7"],   # a hint of a fill; never the only cue (can vanish on rM2)
    "paper": GREYS["grey-0"],
    "knockout": GREYS["grey-0"],        # behind labels and tags placed over lines
}

# Greyscale stand-ins for the accents: on an rM2 only three fills tell apart reliably next to each
# other; a fourth category needs a label or a pattern (docs/design-system.md, "Fills vs patterns").
_GREY_ACCENTS = (("ink", "surface-strong"), ("ink-2", "surface"), ("muted", "surface-faint"))

# Paper Pro pen colours (rmscene) nearest each accent: what movable strokes are drawn in.
_ACCENT_PENS = {"blue": si.PenColor.BLUE, "red": si.PenColor.RED, "green": si.PenColor.GREEN,
                "amber": si.PenColor.YELLOW, "violet": si.PenColor.MAGENTA, "teal": si.PenColor.CYAN}


def make_palette(tokens: Mapping[str, str], color: bool) -> dict[str, str]:
    out = dict(tokens)
    for i, (name, ink, tint) in enumerate(PRO_ACCENTS, 1):
        if color:
            out[f"accent-{i}"], out[f"accent-{i}-tint"] = ink, tint
        else:
            g_ink, g_tint = _GREY_ACCENTS[(i - 1) % len(_GREY_ACCENTS)]
            out[f"accent-{i}"], out[f"accent-{i}-tint"] = out[g_ink], out[g_tint]
    # A pair of groups to tell apart: blue against red holds up for the common colour blindnesses too;
    # on greyscale they differ in fill (solid against hatched), which is the template's job.
    out["pair-a"], out["pair-a-tint"] = (out["accent-1"], out["accent-1-tint"]) if color else (
        out["ink"], out["surface-strong"])
    out["pair-b"], out["pair-b-tint"] = (out["accent-2"], out["accent-2-tint"]) if color else (
        out["ink"], out["surface"])
    return out


# --------------------------------------------------------------------------- lines and spacing


@dataclass(frozen=True)
class Lines:
    """Line weights in mm. 1 px is 0.112 mm on the rM2, 0.096 mm on the Move: anything under about
    2 px breaks up into a dotted, uneven line on e-ink, so 0.25 mm is the floor."""

    hairline: float = 0.25  # the thinnest printed line; ink or `rule` grey only
    rule: float = 0.3       # writing lines, table grids
    line: float = 0.4       # outlines, frames, `guide` grey allowed from here
    strong: float = 0.6     # emphasis: borders of the main area
    heavy: float = 1.0      # the one thing that must stand out
    dot: float = 0.35       # dotted lines: thinner dots vanish
    dot_gap: float = 1.2
    hatch: float = 0.25     # pattern lines (only when a fill can't do it)
    hatch_pitch: float = 1.4


@dataclass(frozen=True)
class Spacing:
    """Spacing in mm. Everything sits on a 1 mm grid and uses the steps below."""

    unit: float = 1.0
    steps: tuple[float, ...] = (1, 2, 3, 4, 6, 8, 12, 16)
    margin: float = 8.0      # page edge to content
    gutter: float = 4.0      # between columns and blocks
    toolbar: float = 14.0    # kept free at the left edge: the open toolbar covers it (safe_area)
    knockout_pad: float = 0.6  # white margin round a label knocked out of lines behind it
    write_pitch: float = 8.0   # ruled writing lines: comfortable handwriting with the Marker


DEVICE_MARGINS = {"rm2": 8.0, "pro": 9.0, "move": 5.0}


# --------------------------------------------------------------------------- the style


@dataclass(frozen=True)
class Style:
    name: str
    device: Device
    color_ok: bool                 # the theme uses colour (accents are hues, not greys)
    text: Mapping[str, TextStyle]
    palette: Mapping[str, str]
    lines: Lines = Lines()
    spacing: Spacing = Spacing()
    pens: Mapping[str, si.PenColor] = field(default_factory=dict)

    # ---- conversion
    def mm(self, millimetres: float) -> float:
        return self.device.mm(millimetres)

    # ---- type
    def type(self, role: str) -> TextStyle:
        try:
            return self.text[role]
        except KeyError:
            raise ValueError(f"unknown text role {role!r}; choose from {', '.join(ROLES)}") from None

    def font(self, role: str) -> str:
        return self.type(role).font

    def size(self, role: str) -> float:
        """The role's font size in device px."""
        return self.mm(self.type(role).size_mm)

    def tracking(self, role: str, size: float | None = None) -> float:
        """Extra px between characters for the role at `size` px (default: its own size)."""
        t = self.type(role)
        return t.tracking * (self.size(role) if size is None else size)

    @property
    def fonts(self) -> tuple[str, ...]:
        return tuple(sorted({t.font for t in self.text.values()}))

    # ---- colour
    def color(self, token: str) -> str:
        """A palette token ("muted", "accent-2-tint") or a literal "#RRGGBB" as is."""
        if token.startswith("#"):
            return token
        try:
            return self.palette[token]
        except KeyError:
            raise ValueError(f"unknown colour token {token!r}; choose from {', '.join(self.palette)} "
                             "or give #RRGGBB") from None

    def pen(self, token: str) -> si.PenColor:
        """The pen colour movable strokes in this token's colour are drawn with."""
        return self.pens.get(token, si.PenColor.BLACK)

    # ---- lines
    def line(self, name: str) -> float:
        """A line weight (Lines field name) in device px."""
        return self.mm(getattr(self.lines, name))

    # ---- drawing helpers
    def text_width(self, s: str, role: str, size: float | None = None) -> float:
        t = self.type(role)
        size = self.size(role) if size is None else size
        s = s.upper() if t.caps else s
        return fonts.text_width(s, t.font, size) + t.tracking * size * max(len(s) - 1, 0)

    def draw_text(self, p, s: str, x: float, y: float, role: str, *, size: float | None = None,
                  color: str | None = None, align: str = "left", rotate: float = 0):
        """`s` in the role's font, size, colour, case and tracking, baseline at (x, y)."""
        t = self.type(role)
        size = self.size(role) if size is None else size
        s = s.upper() if t.caps else s
        p.text(s, x, y, t.font, size, self.color(color or t.color), align, rotate,
               char_space=t.tracking * size)

    def knockout_text(self, p, s: str, x: float, y: float, role: str, *, size: float | None = None,
                      color: str | None = None, align: str = "left") -> Rect:
        """Like draw_text, on a white box that hides the lines behind the label; returns the box."""
        t = self.type(role)
        size = self.size(role) if size is None else size
        w = self.text_width(s, role, size)
        x0 = {"left": x, "center": x - w / 2, "right": x - w}[align]
        pad = self.mm(self.spacing.knockout_pad)
        m = fonts.font(t.font)
        top = y - (m.cap_height if (t.caps or s[:1].isupper() or s[:1].isdigit()) else m.x_height) * size
        descent = 0.22 * size if any(c in s for c in "gjpqy,") and not t.caps else 0.0
        box = Rect(x0 - pad, top - pad, w + 2 * pad, (y + descent) - top + 2 * pad)
        p.rect(box, fill=self.color("knockout"), radius=pad)
        self.draw_text(p, s, x, y, role, size=size, color=color, align=align)
        return box

    def margin(self) -> float:
        """The page margin in px for this device."""
        return self.mm(self.spacing.margin)

    def safe_area(self, landscape: bool = False) -> Rect:
        """Where a page's content goes, in px: inside the margin, and clear of the strip at the left
        edge that the tablet's toolbar covers when it's open."""
        w, h = page_size(self.device, landscape)
        m = self.margin()
        left = max(m, self.mm(self.spacing.toolbar))
        return Rect(left, m, w - left - m, h - 2 * m)


def _scaled(text: Mapping[str, TextStyle], device_key: str) -> dict[str, TextStyle]:
    scale = DEVICE_TYPE_SCALE.get(device_key, {})
    return {role: replace(t, size_mm=round(t.size_mm * scale.get(role, 1.0), 2)) for role, t in text.items()}


_registered: dict[str, Callable[[Device], Style]] = {}


def register_theme(name: str, factory: Callable[[Device], "Style"]) -> None:
    """Add a design theme: `factory(device)` returns its Style. Registering a name again replaces it."""
    if name in ("default", "color"):
        raise ValueError(f"{name!r} is a built-in theme")
    _registered[name] = factory
    if name not in THEMES:
        THEMES.append(name)
    _style.cache_clear()


def _installed(text: Mapping[str, TextStyle]) -> dict[str, TextStyle]:
    """Each role in its preferred font if a font folder has it, else in the bundled fallback."""
    return {role: t if fonts.has_font(t.font) or t.font not in FALLBACK else replace(t, font=FALLBACK[t.font])
            for role, t in text.items()}


@cache
def _style(theme: str, device: Device, font_dirs: tuple) -> Style:
    if theme in _registered:
        return _registered[theme](device)
    color = theme == "color"
    palette = make_palette(SYSTEM_GREY_TOKENS, color)
    pens = {}
    if color:
        for i, (name, _, _) in enumerate(PRO_ACCENTS, 1):
            pens[f"accent-{i}"] = _ACCENT_PENS[name]
        pens["pair-a"], pens["pair-b"] = pens["accent-1"], pens["accent-2"]
    spacing = Spacing(margin=DEVICE_MARGINS.get(device.key, Spacing.margin))
    return Style(theme, device, color, _installed(_scaled(SYSTEM_TEXT, device.key)), palette, Lines(), spacing, pens)


def get_style(theme: str, device: Device | str) -> Style:
    """The theme ("default", "color" or a registered one) resolved for a device."""
    if theme not in THEMES:
        raise ValueError(f"unknown design theme {theme!r}; choose from {', '.join(THEMES)}")
    return _style(theme, get_device(device), tuple(fonts.font_dirs()))  # new font folders, new styles


# --------------------------------------------------------------------------- contrast


def _linear(c: int) -> float:
    v = c / 255
    return v / 12.92 if v <= 0.04045 else ((v + 0.055) / 1.055) ** 2.4


def _rgb(hex_color: str) -> tuple[int, int, int]:
    h = hex_color.lstrip("#")
    return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)


def luminance(hex_color: str) -> float:
    """WCAG relative luminance (0 black .. 1 white)."""
    r, g, b = (_linear(c) for c in _rgb(hex_color))
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def contrast(a: str, b: str = "#FFFFFF") -> float:
    """WCAG 2 contrast ratio of two colours (1 .. 21)."""
    la, lb = sorted((luminance(a), luminance(b)), reverse=True)
    return (la + 0.05) / (lb + 0.05)


def lab(hex_color: str) -> tuple[float, float, float]:
    """CIE L*a*b* (D65) of an sRGB colour."""
    r, g, b = (_linear(c) for c in _rgb(hex_color))
    x = (0.4124 * r + 0.3576 * g + 0.1805 * b) / 0.95047
    y = 0.2126 * r + 0.7152 * g + 0.0722 * b
    z = (0.0193 * r + 0.1192 * g + 0.9505 * b) / 1.08883

    def f(t):
        return t ** (1 / 3) if t > 0.008856 else 7.787 * t + 16 / 116
    return 116 * f(y) - 16, 500 * (f(x) - f(y)), 200 * (f(y) - f(z))


def delta_e(a: str, b: str) -> float:
    """CIE76 colour difference."""
    return sum((p - q) ** 2 for p, q in zip(lab(a), lab(b))) ** 0.5


def grey_uses(hex_color: str) -> tuple[str, ...]:
    """What a grey may be used for on white paper, by the contrast floors: text, line, guide, fill."""
    c = contrast(hex_color)
    uses = [use for use in ("text", "line", "guide") if c >= MIN_CONTRAST[use]]
    if luminance(hex_color) >= luminance(MAX_FILL_INK) and hex_color.upper() != "#FFFFFF":
        uses.append("fill")
    return tuple(uses)
