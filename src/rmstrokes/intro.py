"""The intro page: an optional first page explaining how to use the document on the tablet.

Two parts. The basics, the same for every document: six illustrated cards in a grid (pick the
layer, lasso, drag, write, show or hide, and "Try it" with one practice token you can really
lasso and drag). Then each template's own part (``IntroSpec``): a title, a few short steps and,
by default, a miniature of the template's first page, drawn from that page as built.

The cards show the template's own token when its IntroSpec has one (a word tag, a dot, a part),
and a generic numbered disc otherwise; the practice token is that same token, in real strokes.

The page always speaks in the design system's own voice (design.Style "default"; "color" on a
colour tablet, where the selection loop, step numbers and the selected layer take the first accent),
whatever the template's own theme. The illustrations are one small set of "scenes" drawn with one
line weight, one corner radius and a stylus, echoing the tablet's own layer panel and selection
tool in a simplified form. docs/intro.md has the layout and the illustration rules.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, replace
from typing import Callable, Sequence

from reportlab.lib.utils import simpleSplit
from shapely.geometry import Point, box

from . import fonts
from .design import Style, get_style
from .devices import Device
from .geometry import Rect, page_size
from .layers import Layer, Page
from .pdf import Painter, draw_strokes
from .tokens import NameTag, Token, TokenArt, token_art
from .vectorize import Stroke, resample

PRACTICE_LAYER = "Practice"
SUBTITLE = "How to use it on your reMarkable"
FOOTER = "Turn the page to begin."


@dataclass(frozen=True)
class IntroSpec:
    """A template's part of the intro page. Keep each step to one short sentence, verb first."""

    title: str
    steps: tuple[str, ...] = ()
    layer: str = ""        # the layer its movable things are on ("Words")
    thing: str = "token"   # what you move ("word", "part")
    handwriting: str = ""  # its empty layer for notes, if any
    # A miniature of the template's first page (True), a drawing of your own
    # (fn(painter, rect)), or nothing (False).
    example: bool | Callable[[Painter, Rect], None] = True
    name_tags: bool = True  # its tokens have a tag to write a name in
    # Its own token as its page draws it, at a given size: fn(device, size_mm) -> TokenArt (see
    # token_maker). The basics cards and the practice token use it; None: a generic numbered disc.
    token: Callable[[Device, float], TokenArt] | None = None
    # Labels the steps rely on besides the “quoted” ones (group names, "A–Z"): each must be printed
    # on the template's first page or name one of its layers (templates should test that).
    terms: tuple[str, ...] = ()


def token_maker(token: Token) -> Callable[[Device, float], TokenArt]:
    """An IntroSpec.token for a token of the engine: `token` scaled to `size_mm` wide, its name
    tag and pen with it."""
    def make(device: Device, size_mm: float) -> TokenArt:
        k = size_mm / token.size_mm
        tag = token.name_tag and replace(token.name_tag, width_mm=round(token.name_tag.width_mm * k, 2),
                                         height_mm=round(token.name_tag.height_mm * k, 2),
                                         overlap_mm=round(token.name_tag.overlap_mm * k, 2))
        return token_art(replace(token, size_mm=round(size_mm, 2), pen_mm=round(token.pen_mm * min(k, 1.5), 3),
                                 height_mm=token.height_mm and round(token.height_mm * k, 2), name_tag=tag),
                         device)
    return make


def intro_style(style: Style | None, device: Device) -> Style:
    """The style the intro page draws with: the system's own, in colour on a colour tablet and in
    greys otherwise, whatever the template's theme (`style` is ignored): the intro
    is the tablet's how-to, the same in every document."""
    return get_style("color" if device.color else "default", device)


# --------------------------------------------------------------------------- the basics

@dataclass(frozen=True)
class Step:
    """One basics card: a title, one short sentence, and its scene."""

    title: str
    text: str
    scene: Callable  # (painter, rect, kit)


def _quoted(names: Sequence[str]) -> str:
    return " or ".join(f"“{n}”" for n in dict.fromkeys(names))


def basics(parts: Sequence[IntroSpec]) -> list[Step]:
    """The six cards for a document made of these template parts."""
    layer = _quoted([s.layer for s in parts if s.layer])
    thing = " or ".join(dict.fromkeys(s.thing for s in parts)) or "token"
    notes = [s.handwriting for s in parts if s.handwriting]
    tags = any(s.name_tags for s in parts)
    things = list(dict.fromkeys(s.thing for s in parts))
    own = any(s.token and (s.name_tags or not tags) for s in parts)  # as _Layout picks the demo token
    practice = things[0] if len(things) == 1 and own else "token"
    write = (Step("Name it", "Write a name in the tag, on that layer.", _scene_name) if tags else
             Step("Take notes", f"Pick {_quoted(notes[:1])} and write with the pen." if notes else
                  "Take the pen and write anywhere.", _scene_notes))
    return [
        Step("Pick the layer", f"Open Layers and tap {layer}." if layer else
             "Open Layers and tap the one you move things on.", _scene_layers),
        Step("Lasso it", f"Circle a {thing} with the selection tool.", _scene_lasso),
        Step("Drag it", "Drag the selection to its new place.", _scene_drag),
        write,
        Step("Show or hide", f"Tap the eye to hide {_quoted(notes[:1])}." if notes else
             "Tap a layer's eye to hide it.", _scene_visibility),
        Step("Try it", f"Move this {practice} onto its outline.", _scene_practice),
    ]


# --------------------------------------------------------------------------- the drawing kit

class Kit:
    """Colours, the one line weight and the one radius every scene draws with."""

    def __init__(self, style: Style, layer_names: Sequence[str], hidden: str = "", tags: bool = True,
                 maker: Callable[[Device, float], TokenArt] | None = None):
        self.style = style
        self.device = style.device
        c = style.color
        self.ink, self.ink2, self.muted, self.paper = c("ink"), c("ink-2"), c("muted"), c("paper")
        self.guide = c("guide")
        self.accent = c("accent-1") if style.color_ok else c("ink")
        self.tint = c("accent-1-tint") if style.color_ok else c("surface")
        self.lw = style.line("line")          # every outline in every scene
        self.fine = style.line("hairline")    # small inner details only
        self.radius = style.mm(1.2)           # every rounded corner
        self.layer_names = list(layer_names) or ["Tokens"]
        self.hidden = hidden                  # the layer the visibility scene hides
        self.tags = tags                      # the demo token has a name tag
        self.maker = maker                    # the template's own token (IntroSpec.token), if any

    def mm(self, v: float) -> float:
        return self.device.mm(v)

    def font(self, role: str) -> str:
        return self.style.font(role)

    # ---- pieces every scene shares

    def token(self, height: float) -> TokenArt:
        """The demo token, `height` px tall in all: the template's own, or a numbered disc (with a
        name tag if the templates' tokens have one)."""
        if self.maker is not None:
            probe = self.maker(self.device, 10.0)
            return self.maker(self.device, 10.0 * height / probe.height)
        size = height / (1.45 if self.tags else 1.05) / self.mm(1)
        tag = NameTag(width_mm=round(size * 1.7, 2), height_mm=round(max(size * 0.52, 2.6), 2),  # its round box needs 2.6
                      overlap_mm=round(size * 0.08, 2)) if self.tags else None
        return token_art(Token("circle", size_mm=round(size, 2), style="outline", pen_mm=0.4, number=7,
                               name_tag=tag), self.device)

    def pair(self, r: Rect, height: float, room: float) -> TokenArt:
        """The demo token at `height`, or smaller so two of them and `room` fit across `r`."""
        art = self.token(height)
        if 2 * art.width + room > r.w:
            art = self.token(height * (r.w - room) / (2 * art.width))
        return art

    def stylus(self, p: Painter, tip: tuple[float, float], length: float, angle: float = 58.0):
        """A stylus touching the page at `tip`, its body up and to the right."""
        a = math.radians(angle)
        u, n = (math.cos(a), -math.sin(a)), (math.sin(a), math.cos(a))
        half, cone = length * 0.075, length * 0.2

        def at(along, across):
            return tip[0] + u[0] * along + n[0] * across, tip[1] + u[1] * along + n[1] * across
        cap = [at(length + half * math.sin(t), half * math.cos(t))
               for t in (math.pi * i / 8 for i in range(9))]
        body = [tip, at(cone, half), *cap, at(cone, -half)]
        p.c.setLineJoin(1)
        p.polyline(body, self.lw, self.ink, closed=True, fill=self.paper)
        p.line(*at(cone, half), *at(cone, -half), self.lw, self.ink)
        p.polyline([tip, at(cone * 0.4, half * 0.4), at(cone * 0.4, -half * 0.4)], self.fine, self.ink,
                   closed=True, fill=self.ink)

    def fit_stylus(self, p: Painter, tip, r: Rect, length: float):
        """A stylus at `tip`, shortened to stay inside `r`."""
        a = math.radians(58.0)
        room = min((tip[1] - r.y) / math.sin(a), (r.right - tip[0]) / math.cos(a)) - self.lw * 2
        self.stylus(p, tip, max(min(length, room), length * 0.4))

    def eye(self, p: Painter, cx: float, cy: float, s: float, color: str, open_: bool = True):
        """The layer panel's eye, `s` px wide; struck through when the layer is hidden."""
        n = 12
        top = [(cx - s / 2 + s * i / n, cy - s * 0.3 * math.sin(math.pi * i / n)) for i in range(n + 1)]
        bottom = [(x, 2 * cy - y) for x, y in reversed(top)]
        p.polyline(top + bottom[1:], self.lw, color, closed=True)
        p.circle(cx, cy, s * 0.13, fill=color)
        if not open_:
            p.line(cx - s * 0.42, cy + s * 0.38, cx + s * 0.42, cy - s * 0.38, self.lw, color)

    def selection(self, p: Painter, box: Rect):
        """The selection box round what the lasso took: a thin frame with corner handles."""
        p.rect(box, stroke=self.ink2, width=self.fine)
        h = self.mm(1.3)
        for x, y in ((box.x, box.y), (box.right, box.y), (box.x, box.bottom), (box.right, box.bottom)):
            p.rect(Rect.around(x, y, h, h), fill=self.paper, stroke=self.ink, width=self.fine)

    def dashed(self, p: Painter, points, color: str, closed: bool = False):
        c = p.c
        c.saveState()
        p.dash("dashed", self.lw, self.mm(1.0), self.mm(1.8))
        p.polyline(points, self.lw, color, closed=closed)
        c.restoreState()

    def ghost(self, p: Painter, art: TokenArt, cx: float, cy: float):
        """Where a token was, or goes: its outline (the disc and tag, or the template's own
        token's outline), dotted in the guide grey."""
        x0, y0 = cx - art.width / 2, cy - art.height / 2
        if self.maker is not None:
            region = art.outline(cx, cy)
            lines = [g.exterior for g in getattr(region, "geoms", [region])]
        else:
            sh = art.shape.moved(x0, y0)
            disc = Point(*sh.center).buffer(min(sh.w, sh.h) / 2, quad_segs=16)
            lines = [disc.exterior]
        if art.tag and self.maker is None:
            t = art.tag.moved(x0, y0)
            rr = min(self.mm(1), t.h / 3)
            tag = box(t.x + rr, t.y + rr, t.right - rr, t.bottom - rr).buffer(rr, quad_segs=6)
            lines.append(tag.exterior.difference(disc))
        c = p.c
        c.saveState()
        p.dash("dotted", self.lw, self.mm(0.9))
        for g in lines:
            for part in getattr(g, "geoms", [g]):
                p.polyline(list(part.coords), self.lw, self.guide)
        c.restoreState()

    def arrow(self, p: Painter, a, b, lift: float):
        """A curved motion arrow from `a` to `b`, bowed `lift` px upwards."""
        mx, my = (a[0] + b[0]) / 2, (a[1] + b[1]) / 2 - lift
        pts = [((1 - t) ** 2 * a[0] + 2 * (1 - t) * t * mx + t * t * b[0],
                (1 - t) ** 2 * a[1] + 2 * (1 - t) * t * my + t * t * b[1]) for t in (i / 24 for i in range(25))]
        p.c.setLineCap(1)
        p.c.setLineJoin(1)
        p.polyline(pts, self.lw, self.accent)
        (x0, y0), (x1, y1) = pts[-3], pts[-1]
        ang = math.atan2(y1 - y0, x1 - x0)
        head = self.mm(1.6)
        p.polyline([(x1 - head * math.cos(ang - 0.5), y1 - head * math.sin(ang - 0.5)), (x1, y1),
                    (x1 - head * math.cos(ang + 0.5), y1 - head * math.sin(ang + 0.5))], self.lw, self.accent)

    def text_fit(self, p: Painter, s: str, x: float, y: float, role: str, size: float, width: float,
                 color: str, align: str = "left"):
        face = self.font(role)
        size = min(size, size * width / max(fonts.text_width(s, face, size), 1e-6))
        p.text(s, x, y, face, size, color, align)

    def layer_panel(self, p: Painter, r: Rect, rows: Sequence[tuple[str, bool, bool]]):
        """The layers panel: a header and one row per (name, selected, visible). Returns each
        row's rect and its eye's centre."""
        rh = min(r.h / (len(rows) + 0.9), self.mm(7.5))
        head = rh * 0.9
        panel = Rect(r.x, r.y + (r.h - head - rh * len(rows)) / 2, r.w, head + rh * len(rows))
        p.rect(panel, fill=self.paper, stroke=self.ink, width=self.lw, radius=self.radius)
        pad = rh * 0.32
        self.text_fit(p, "Layers", panel.x + pad, panel.y + head * 0.64, "caption", head * 0.42,
                      panel.w * 0.5, self.ink)
        out = []
        for i, (name, selected, visible) in enumerate(rows):
            row = Rect(panel.x, panel.y + head + i * rh, panel.w, rh)
            p.line(row.x, row.y, row.right, row.y, self.fine, self.muted)
            if selected:
                inner = Rect(row.x + self.lw * 2, row.y + self.lw * 2, row.w - self.lw * 4, row.h - self.lw * 4)
                p.rect(inner, fill=self.tint, radius=self.radius * 0.6)
            thumb = Rect(row.x + pad, row.y + rh * 0.2, rh * 0.45, rh * 0.6)
            p.rect(thumb, fill=self.paper, stroke=self.ink if visible else self.muted, width=self.fine,
                   radius=self.radius * 0.4)
            if visible:
                for j in range(2):
                    y = thumb.y + thumb.h * (0.38 + 0.26 * j)
                    p.line(thumb.x + thumb.w * 0.22, y, thumb.right - thumb.w * (0.22 + 0.2 * j), y, self.fine,
                           self.ink2)
            eye = (row.right - pad - rh * 0.3, row.center[1])
            tx = thumb.right + pad
            role = "heading" if selected else "label"
            self.text_fit(p, name, tx, row.center[1] + rh * 0.13, role, rh * 0.36, eye[0] - rh * 0.4 - tx,
                          self.ink if visible else self.muted)
            self.eye(p, *eye, rh * 0.5, self.ink if visible else self.muted, visible)
            out.append((row, eye))
        return out


def _freehand_loop(r: Rect, pad: float) -> list[tuple[float, float]]:
    """A smooth, slightly uneven closed loop round `r`, as a hand draws the lasso: an oval through
    the box's corners and `pad` beyond, starting low on the right and running a little past its start."""
    cx, cy = r.center
    rx, ry = r.w / 2 * math.sqrt(2) + pad, r.h / 2 * math.sqrt(2) + pad
    n, start = 96, 0.35
    pts = []
    for i in range(n + 8):  # 8 more: past the start, slightly inside
        a = start + 2 * math.pi * i / n
        k = 1 + 0.035 * math.sin(2 * a + 0.9) + 0.015 * math.sin(3 * a + 2.1) - 0.004 * max(0, i - n)
        pts.append((cx + rx * k * math.cos(a), cy + ry * k * math.sin(a)))
    return pts


# Handwriting: "Ana" as a hand writes it, on a 0..9.4 x 0..6 grid (y down, baseline at 6).
_ANA = (
    [(0.0, 6.0), (0.9, 3.2), (1.7, 0.4), (2.0, 0.2), (2.3, 1.4), (2.9, 4.4), (3.3, 6.0)],
    [(0.8, 3.9), (1.9, 3.6), (2.9, 3.5)],
    [(3.6, 3.4), (3.9, 4.6), (4.0, 6.0), (4.1, 4.2), (4.6, 3.1), (5.3, 3.0), (5.6, 3.9), (5.7, 5.5),
     (6.1, 6.0), (6.6, 5.6)],
    [(8.4, 3.6), (7.7, 3.0), (6.9, 3.4), (6.6, 4.8), (7.1, 6.0), (7.9, 5.4), (8.4, 3.2), (8.5, 5.2),
     (8.9, 6.0), (9.4, 5.6)],
)


def _smooth(points, steps: int = 6):
    """A Catmull-Rom curve through the points."""
    pts = [points[0], *points, points[-1]]
    out = []
    for i in range(1, len(pts) - 2):
        p0, p1, p2, p3 = pts[i - 1], pts[i], pts[i + 1], pts[i + 2]
        for j in range(steps):
            t = j / steps
            out.append(tuple(0.5 * (2 * p1[k] + (-p0[k] + p2[k]) * t + (2 * p0[k] - 5 * p1[k] + 4 * p2[k] - p3[k]) * t * t
                                    + (-p0[k] + 3 * p1[k] - 3 * p2[k] + p3[k]) * t ** 3) for k in (0, 1)))
    out.append(points[-1])
    return out


def handwriting(x: float, y: float, height: float, pen: float) -> tuple[list[Stroke], tuple[float, float]]:
    """"Ana" in a hand, its baseline-left corner at (x, y), `height` px tall; and where the pen
    stopped."""
    k = height / 6.0
    strokes = []
    for line in _ANA:
        pts = [(x + (px - (py - 6) * 0.18) * k, y + (py - 6) * k) for px, py in _smooth(line)]
        strokes.append(Stroke(tuple(resample(pts, 2.0)), pen))
    return strokes, strokes[-1].points[-1]


HANDWRITING_W = 9.4 / 6.0 + 0.18  # width of the handwriting per px of height


# --------------------------------------------------------------------------- the scenes

def _scene_layers(p: Painter, r: Rect, kit: Kit):
    names = kit.layer_names[:3]
    w = min(r.w * 0.82, r.h * 1.5)
    rows = kit.layer_panel(p, Rect(r.x + (r.w - w) / 2, r.y, w, r.h), [(n, i == 0, True) for i, n in enumerate(names)])
    row = rows[0][0]
    kit.fit_stylus(p, (row.x + row.w * 0.62, row.center[1] + row.h * 0.12), r, r.h * 0.48)


def _scene_visibility(p: Painter, r: Rect, kit: Kit):
    names = kit.layer_names[:3]
    hidden = kit.hidden if kit.hidden in names else names[-1]
    w = min(r.w * 0.82, r.h * 1.5)
    rows = kit.layer_panel(p, Rect(r.x + (r.w - w) / 2, r.y, w, r.h),
                           [(n, i == 0, n != hidden) for i, n in enumerate(names)])
    eye = rows[names.index(hidden)][1]
    kit.fit_stylus(p, (eye[0] + kit.mm(0.6), eye[1] + kit.mm(0.9)), r, r.h * 0.48)


def _scene_lasso(p: Painter, r: Rect, kit: Kit):
    art = kit.token(r.h * 0.5)
    cx, cy = r.x + r.w * 0.44, r.center[1]
    region = art.outline(cx, cy)
    x0, y0, x1, y1 = region.bounds
    pad = kit.mm(0.6)
    sel = Rect(x0 - pad, y0 - pad, x1 - x0 + 2 * pad, y1 - y0 + 2 * pad)
    kit.selection(p, sel)
    draw_strokes(p, art.placed(cx, cy))
    loop = _freehand_loop(sel, kit.mm(1.8))
    kit.dashed(p, loop, kit.accent)
    kit.fit_stylus(p, loop[-1], r, r.h * 0.48)


def _scene_drag(p: Painter, r: Rect, kit: Kit):
    pad = kit.mm(1.5)
    art = kit.pair(r, r.h * 0.5, pad * 7)
    a = (r.x + art.width / 2 + pad, r.center[1] + r.h * 0.12)
    b = (r.right - art.width / 2 - pad * 3.5, r.center[1] + r.h * 0.12)
    kit.ghost(p, art, *a)
    kit.arrow(p, (a[0] + art.width * 0.2, a[1] - art.height * 0.62),
              (b[0] - art.width * 0.62, b[1] - art.height * 0.5), r.h * 0.14)
    x0, y0, x1, y1 = art.outline(*b).bounds
    s = kit.mm(0.9)
    kit.selection(p, Rect(x0 - s, y0 - s, x1 - x0 + 2 * s, y1 - y0 + 2 * s))
    draw_strokes(p, art.placed(*b))
    kit.fit_stylus(p, (b[0] + art.width * 0.2, b[1] + art.height * 0.05), r, r.h * 0.48)


def _scene_name(p: Painter, r: Rect, kit: Kit):
    art = kit.token(r.h * 0.78)
    cx, cy = r.x + r.w * 0.42, r.center[1]
    draw_strokes(p, art.placed(cx, cy))
    tag = art.tag.moved(cx - art.width / 2, cy - art.height / 2)
    h = tag.h * 0.5
    w = HANDWRITING_W * h
    ink, end = handwriting(tag.center[0] - w / 2, tag.center[1] + h / 2, h, kit.mm(0.35))
    draw_strokes(p, ink)
    kit.fit_stylus(p, end, r, r.h * 0.5)


def _scene_notes(p: Painter, r: Rect, kit: Kit):
    sheet = Rect(r.x + r.w * 0.12, r.y + r.h * 0.08, r.w * 0.62, r.h * 0.84)
    p.rect(sheet, fill=kit.paper, stroke=kit.ink, width=kit.lw, radius=kit.radius)
    pitch = sheet.h / 4
    for i in range(1, 4):
        y = sheet.y + pitch * i
        p.line(sheet.x + kit.mm(2), y, sheet.right - kit.mm(2), y, kit.fine, kit.muted)
    h = pitch * 0.55
    ink, end = handwriting(sheet.x + kit.mm(2.5), sheet.y + pitch - kit.fine * 2, h, kit.mm(0.35))
    draw_strokes(p, ink)
    y2 = sheet.y + pitch * 2 - kit.fine * 2
    wave = [(sheet.x + kit.mm(2.5) + i * kit.mm(0.5), y2 - h * 0.35 * (1 + math.sin(i * 1.3)) / 2)
            for i in range(int((sheet.w * 0.55) / kit.mm(0.5)))]
    p.c.setLineCap(1)
    p.polyline(_smooth(wave, 3), kit.mm(0.35), kit.ink)
    kit.fit_stylus(p, wave[-1], r, r.h * 0.5)


def _practice_geometry(r: Rect, kit: Kit):
    """The practice token and where it goes, in the Try it card's scene."""
    pad = kit.mm(1.5)
    art = kit.pair(r, r.h * 0.62, pad * 4)
    start = (r.x + art.width / 2 + pad, r.center[1] + r.h * 0.08)
    end = (r.right - art.width / 2 - pad, r.center[1] + r.h * 0.08)
    return art, start, end


def _scene_practice(p: Painter, r: Rect, kit: Kit):
    """Only the outline and the arrow: the token itself is real strokes on the practice layer."""
    art, start, end = _practice_geometry(r, kit)
    kit.ghost(p, art, *end)
    if end[0] - start[0] > art.width * 1.3:
        kit.arrow(p, (start[0] + art.width * 0.2, start[1] - art.height * 0.6),
                  (end[0] - art.width * 0.2, end[1] - art.height * 0.6), r.h * 0.14)


# --------------------------------------------------------------------------- layout

class _Layout:
    """Measures and places everything at one scale `k`; `boxes` lists what goes where."""

    def __init__(self, device: Device, landscape: bool, parts: Sequence[tuple[IntroSpec, Page | None]],
                 title: str, style: Style, k: float, with_example: bool, dense: bool = False):
        self.device, self.landscape, self.parts, self.style = device, landscape, parts, style
        self.title = title or parts[0][0].title
        self.k, self.with_example, self.dense = k, with_example, dense  # dense: one more card column
        mm = device.mm
        self.W, self.H = W, H = page_size(device, landscape)
        self.small = small = min(W, H) < mm(110)
        self.margin = style.margin() if small else max(style.margin(), mm(11))
        floor = 2.5

        def size(v):
            return mm(max(v * k, floor))
        self.title_size = mm((7.2 if small else 8.8) * min(1.0, k * 1.1))
        self.sub_size = size(3.6)
        self.caps_size = size(2.8)
        self.card_title = size(3.5)
        self.card_text = size(3.1)
        self.part_title = size(5.4)
        self.step_text = size(3.3)
        self.disc = mm(max(4.4 * k, 4.0))
        self.lead = 1.38
        names = [n for s, _ in parts for n in (s.layer, s.handwriting) if n]
        self.layer_names = list(dict.fromkeys(names))
        notes = [s.handwriting for s, _ in parts if s.handwriting]
        tags = any(s.name_tags for s, _ in parts)
        # The first template's own token that can show the cards' name tag, if one is needed.
        makers = [s.token for s, _ in parts if s.token and (s.name_tags or not tags)]
        self.kit = Kit(style, self.layer_names, notes[0] if notes else "", tags, makers[0] if makers else None)
        self.steps = basics([s for s, _ in parts])
        self.boxes: list[tuple[str, Rect]] = []
        self.ok = self._place()

    def mm(self, v):
        return self.device.mm(v)

    def wrap(self, text, role, size, width):
        """Lines of `text` at most `width` wide, never ending on a single word if a narrower
        measure avoids it."""
        face = self.style.font(role)
        fonts.font(face)
        lines = simpleSplit(text, face, size, width)
        w = width
        while len(lines) > 1 and " " not in lines[-1] and w > width * 0.7:
            w -= size
            narrower = simpleSplit(text, face, size, w)
            if len(narrower) > len(lines):
                break
            lines = narrower
        return lines

    # ---- the pieces

    def header_height(self):
        return self.title_size * 1.05 + self.mm(2.2) + self.sub_size * 1.1

    def card_grid(self, x, y, w, cols):
        """The basics cards in a grid from (x, y), `w` wide: [(step, scene rect, text rect)], bottom."""
        gx, gy = self.mm(6 * self.k), self.mm(7 * self.k)
        cw = (w - gx * (cols - 1)) / cols
        sh = cw * (0.8 if self.dense else 0.5 if self.small else 0.6) * min(1.0, 0.6 + 0.4 * self.k)  # flatten last
        out = []
        for row in range(math.ceil(len(self.steps) / cols)):
            steps = self.steps[row * cols:(row + 1) * cols]
            lines = max(len(self.wrap(s.text, "body", self.card_text, cw)) for s in steps)
            th = self.mm(2.6 * self.k) + self.disc * 1.05 + self.mm(1.2) + lines * self.card_text * self.lead
            for i, s in enumerate(steps):
                cx = x + i * (cw + gx)
                out.append((s, Rect(cx, y, cw, sh), Rect(cx, y + sh, cw, th)))
            y += sh + th + gy
        return out, y - gy

    def part_height(self, spec: IntroSpec, first: Page | None, w):
        box = self.example_box(spec, first, w)
        steps_w = w - box[1] - self.mm(5) if box and box[0] == "right" else w
        head = self.part_title * 1.7
        steps = self.steps_height(spec, steps_w)
        if box is None:
            return head + steps
        if box[0] == "below":
            return head + steps + self.mm(3) + box[2]
        return head + max(steps, box[2])

    def steps_height(self, spec: IntroSpec, w):
        tw = w - self.disc - self.mm(3)
        return sum(len(self.wrap(s, "body", self.step_text, tw)) * self.step_text * self.lead + self.mm(2.2 * self.k)
                   for s in spec.steps)

    def example_box(self, spec: IntroSpec, first: Page | None, w):
        """Where this part's example goes: ("right" | "below", width, height), or None. A
        landscape page goes under the steps at full width, a portrait one beside them."""
        if not (spec.example and self.with_example) or (first is None and not callable(spec.example)):
            return None
        if first is not None and first.landscape:
            pw, ph = page_size(self.device, True)
            return "below", w, min(w * ph / pw, self.mm(70 * self.k))
        bw = w * 0.36
        return "right", bw, min(bw * 4 / 3, self.mm(64 * self.k))

    # ---- placing

    def _place(self) -> bool:
        mm, m = self.mm, self.margin
        W, H = self.W, self.H
        # Inside the style's safe area (clear of the toolbar on the left), with the intro's own margin.
        safe = self.style.safe_area(self.landscape)
        left = max(m, safe.x)
        content = Rect(left, m, W - left - m, H - 2 * m)
        self.content = content
        self.boxes.append(("header", Rect(content.x, m, content.w, self.header_height())))
        self.footer_y = content.bottom - self.sub_size * 0.25  # descenders stay above the margin
        bottom = self.footer_y - self.sub_size * 1.6
        top = m + self.header_height() + mm(7 * self.k)
        self.rule_y = top - mm(3.5 * self.k)
        label_h = self.caps_size * 2.2
        if self.landscape:
            gap = mm(10 * self.k)
            bw = content.w * 0.55
            cols = [Rect(content.x, top, bw, bottom - top),
                    Rect(content.x + bw + gap, top, content.w - bw - gap, bottom - top)]
            grid_cols = 3 + self.dense
        else:
            cols = [Rect(content.x, top, content.w, bottom - top)]
            grid_cols = (3 if content.w >= mm(110) else 2) + self.dense
        basics = cols[0]
        self.boxes.append(("label", Rect(basics.x, top, basics.w, label_h)))
        self.cards, y = self.card_grid(basics.x, top + label_h, basics.w, grid_cols)
        for _, scene, text in self.cards:
            self.boxes += [("scene", scene), ("text", text)]
        col = cols[1] if self.landscape else Rect(content.x, y + mm(9 * self.k), content.w,
                                                  bottom - y - mm(9 * self.k))
        y = col.y
        self.part_rects = []
        for i, (spec, first) in enumerate(self.parts):
            h = self.part_height(spec, first, col.w)
            r = Rect(col.x, y, col.w, h)
            self.part_rects.append(r)
            self.boxes.append(("part", r))
            y += h + mm(7 * self.k)
        lowest = max(r.bottom for _, r in self.boxes)
        return lowest <= bottom + 1e-6 and (not self.landscape or y - mm(7 * self.k) <= bottom + 1e-6)


def _layout(device, landscape, parts, title, style: Style) -> _Layout:
    for dense in (False, True):
        for with_example in (True, False):
            for k in (1.0, 0.94, 0.88, 0.82, 0.76, 0.7, 0.64, 0.58, 0.52):
                lay = _Layout(device, landscape, parts, title, style, k, with_example, dense)
                if lay.ok:
                    return lay
    raise ValueError(f"the intro page doesn't fit on {device.name}: shorten the template steps")


# --------------------------------------------------------------------------- drawing

def _miniature(p: Painter, page: Page, device: Device, r: Rect, kit: Kit | None = None):
    """`page` (background and strokes) scaled into `r`, in a thin rounded frame."""
    pw, ph = page_size(device, page.landscape)
    s = min(r.w / pw, r.h / ph)
    box = Rect(r.x + (r.w - pw * s) / 2, r.y + (r.h - ph * s) / 2, pw * s, ph * s)
    radius = kit.radius if kit else device.mm(1.2)
    c = p.c
    c.saveState()
    clip = c.beginPath()
    clip.roundRect(box.x, box.y, box.w, box.h, radius)
    c.clipPath(clip, stroke=0, fill=0)
    c.translate(box.x, box.y)
    c.scale(s, s)
    mini = Painter(c, device, page.landscape)
    if page.draw is not None:
        page.draw(mini)
    draw_strokes(mini, page.strokes)
    c.restoreState()
    p.rect(box, stroke=kit.ink if kit else "#000000", width=kit.lw if kit else device.mm(0.4), radius=radius)


def _number(p: Painter, lay: _Layout, n: int | str, x: float, y: float):
    """A step number in a ring, its left edge at x, centred on y."""
    kit, d = lay.kit, lay.disc
    p.circle(x + d / 2, y, d / 2 - kit.lw / 2, stroke=kit.accent, width=kit.lw)
    p.label(str(n), x + d / 2, y, lay.style.font("heading"), d * 0.56, kit.ink)


def _draw_card(p: Painter, lay: _Layout, n: int, step: Step, scene: Rect, text: Rect):
    kit = lay.kit
    step.scene(p, scene.inset(lay.mm(0.5)), kit)
    y = text.y + lay.mm(2.6 * lay.k) + lay.disc / 2
    if step.scene is _scene_practice:  # no number: a filled ring with a tick, it's your turn
        d, cx = lay.disc, text.x + lay.disc / 2
        p.circle(cx, y, d / 2, fill=kit.accent)
        p.c.setLineCap(1)
        p.c.setLineJoin(1)
        p.polyline([(cx - d * 0.22, y + d * 0.01), (cx - d * 0.06, y + d * 0.17), (cx + d * 0.23, y - d * 0.16)],
                   kit.lw * 1.2, kit.paper)
    else:
        _number(p, lay, n, text.x, y)
    face = lay.style.font("heading")
    fonts.font(face)
    m = fonts.font(face)
    p.text(step.title, text.x + lay.disc + lay.mm(2), y + m.cap_height * lay.card_title / 2, face, lay.card_title,
           kit.ink)
    y = text.y + lay.mm(2.6 * lay.k) + lay.disc * 1.05 + lay.mm(1.2) + lay.card_text
    for line in lay.wrap(step.text, "body", lay.card_text, text.w):
        p.text(line, text.x, y, lay.style.font("body"), lay.card_text, kit.ink2)
        y += lay.card_text * lay.lead


def _draw_part(p: Painter, lay: _Layout, r: Rect, spec: IntroSpec, first: Page | None):
    kit = lay.kit
    p.text(spec.title, r.x, r.y + lay.part_title, lay.style.font("title"), lay.part_title, kit.ink)
    box = lay.example_box(spec, first, r.w)
    steps_w = r.w - box[1] - lay.mm(5) if box and box[0] == "right" else r.w
    top = r.y + lay.part_title * 1.7
    y = top
    tx = r.x + lay.disc + lay.mm(3)
    face = lay.style.font("body")
    m = fonts.font(face)
    for i, step in enumerate(spec.steps, 1):
        lines = lay.wrap(step, "body", lay.step_text, steps_w - lay.disc - lay.mm(3))
        base = y + lay.step_text
        _number(p, lay, i, r.x, base - m.cap_height * lay.step_text / 2)
        for line in lines:
            p.text(line, tx, base, face, lay.step_text, kit.ink)
            base += lay.step_text * lay.lead
        y += len(lines) * lay.step_text * lay.lead + lay.mm(2.2 * lay.k)
    if box is None:
        return
    where, bw, bh = box
    ex = (Rect(r.right - bw, top, bw, bh) if where == "right" else
          Rect(r.x, top + lay.steps_height(spec, r.w) + lay.mm(3), bw, bh))
    if callable(spec.example):
        spec.example(p, ex)
    else:
        _miniature(p, first, lay.device, ex, kit)


def intro_page(device: Device, parts: Sequence[tuple[IntroSpec, Page | None]], *, landscape: bool = False,
               title: str = "", style: Style | None = None) -> Page:
    """The intro page for a document made from these templates: (IntroSpec, the template's first
    page for the miniature) per template, in order of appearance. `style`: the first template's
    style; see intro_style for what the intro draws with."""
    if not parts:
        parts = [(IntroSpec("Your document"), None)]
    style = intro_style(style, device)
    lay = _layout(device, landscape, parts, title, style)
    page = _render(lay)
    page.layers = [Layer(PRACTICE_LAYER, _practice_strokes(lay))]
    return page


def _practice_strokes(lay: _Layout) -> list[Stroke]:
    for step, scene, _ in lay.cards:
        if step.scene is _scene_practice:
            art, start, _ = _practice_geometry(scene.inset(lay.mm(0.5)), lay.kit)
            return art.placed(*start)
    return []


def _render(lay: _Layout) -> Page:
    style, kit, mm = lay.style, lay.kit, lay.mm

    def draw(p: Painter):
        m, c = lay.margin, lay.content
        p.text(lay.title, c.x, m + lay.title_size * 0.82, style.font("title"), lay.title_size, kit.ink)
        p.text(SUBTITLE, c.x, m + lay.title_size * 1.05 + mm(2.2) + lay.sub_size * 0.8, style.font("italic"),
               lay.sub_size, kit.muted)
        p.line(c.x, lay.rule_y, c.right, lay.rule_y, kit.fine, kit.muted)
        label = next(r for n, r in lay.boxes if n == "label")
        p.text("THE BASICS", label.x, label.y + lay.caps_size * 1.2, style.font("caps"), lay.caps_size, kit.ink2,
               char_space=style.tracking("caps", lay.caps_size))
        for n, (step, scene, text) in enumerate(lay.cards, 1):
            _draw_card(p, lay, n, step, scene, text)
        for r, (spec, first) in zip(lay.part_rects, lay.parts):
            _draw_part(p, lay, r, spec, first)
        p.text(FOOTER, c.x + c.w / 2, lay.footer_y, style.font("italic"), lay.sub_size * 0.9, kit.muted, "center")

    example_fonts = tuple(f for _, first in lay.parts if first is not None for f in first.fonts)
    return Page(draw=draw, layers=[], landscape=lay.landscape, fonts=(*style.fonts, *example_fonts), kind="intro")
