"""Drawing PDF backgrounds in page px.

A ``Painter`` wraps a reportlab canvas so callers draw in device pixels with y pointing down, the
same frame the pen strokes use; pages are sized so 1 device pixel = 72/dpi pt (``Device.pt_per_px``),
which keeps the PDF and the strokes aligned 1:1 on the tablet.
"""
from __future__ import annotations

import math
from contextlib import contextmanager
from typing import Iterable, Sequence

from reportlab.lib.colors import HexColor
from reportlab.pdfgen.canvas import Canvas

from .devices import Device
from .fonts import font
from .geometry import Rect

# Pen colours as printed in a PDF (rmscene PenColor names).
STROKE_COLORS = {"BLACK": "#000000", "GRAY": "#7F7F7F", "WHITE": "#FFFFFF",
                 # The colour pens of the Paper Pro (approximate; a colour panel shows its own shades).
                 "RED": "#D0312D", "BLUE": "#2B5FB8", "GREEN": "#2E8B3E", "YELLOW": "#E8C21A",
                 "PINK": "#E06AA6", "CYAN": "#1FA5C2", "MAGENTA": "#B0359A"}


class Painter:
    """A reportlab canvas set up to draw in page px with y pointing down."""

    def __init__(self, canvas: Canvas, device: Device, landscape: bool = False):
        self.c = canvas
        self.device = device
        self.landscape = landscape

    @property
    def size(self) -> tuple[float, float]:
        """(width, height) of the page as shown, in px."""
        d = self.device
        return (d.height, d.width) if self.landscape else (d.width, d.height)

    def mm(self, millimetres: float) -> float:
        return self.device.mm(millimetres)

    def begin_page(self):
        k = self.device.pt_per_px
        self.c.translate(0, self.size[1] * k)
        self.c.scale(k, -k)

    @contextmanager
    def local(self, x: float, y: float, angle: float = 0):
        """Draw in a frame with its origin at page px (x, y), turned `angle` degrees clockwise."""
        self.c.saveState()
        self.c.translate(x, y)
        self.c.rotate(angle)  # y points down, so a positive angle turns clockwise on the page
        try:
            yield
        finally:
            self.c.restoreState()

    def text(self, s: str, x: float, y: float, font_name: str, size: float, color: str,
             align: str = "left", rotate: float = 0, char_space: float = 0):
        """Draw `s` with its baseline anchor at (x, y), rotated (degrees, clockwise on the page),
        `char_space` px added between characters (tracking)."""
        if not s:
            return
        font(font_name)
        c = self.c
        c.saveState()
        c.translate(x, y)
        c.scale(1, -1)  # glyphs upright again
        if rotate:
            c.rotate(-rotate)
        c.setFont(font_name, size)
        c.setFillColor(HexColor(color))
        if align == "center":
            c.drawCentredString(0, 0, s, charSpace=char_space)
        elif align == "right":
            c.drawRightString(0, 0, s, charSpace=char_space)
        else:
            c.drawString(0, 0, s, charSpace=char_space)
        c.restoreState()

    def label(self, s: str, cx: float, cy: float, font_name: str, size: float, color: str,
              rotate: float = 0):
        """Draw a short label optically centred on (cx, cy): digits and capitals on their cap height,
        lowercase on the x-height."""
        m = font(font_name)
        h = m.cap_height if (s.isdigit() or s.isupper()) else m.x_height
        # Shift the baseline down (in the label's own frame) by half the visual height.
        a = math.radians(rotate)
        dy = h * size / 2
        self.text(s, cx - dy * math.sin(a), cy + dy * math.cos(a), font_name, size, color,
                  "center", rotate)

    def line(self, x0, y0, x1, y1, width: float, color: str):
        c = self.c
        c.setStrokeColor(HexColor(color))
        c.setLineWidth(width)
        c.line(x0, y0, x1, y1)

    def rect(self, r: Rect, *, fill: str | None = None, stroke: str | None = None, width: float = 0,
             radius: float = 0):
        c = self.c
        if fill:
            c.setFillColor(HexColor(fill))
        if stroke:
            c.setStrokeColor(HexColor(stroke))
            c.setLineWidth(width)
        if radius:
            c.roundRect(r.x, r.y, r.w, r.h, radius, stroke=int(bool(stroke)), fill=int(bool(fill)))
        else:
            c.rect(r.x, r.y, r.w, r.h, stroke=int(bool(stroke)), fill=int(bool(fill)))

    def circle(self, cx: float, cy: float, r: float, *, fill: str | None = None,
               stroke: str | None = None, width: float = 0):
        c = self.c
        if fill:
            c.setFillColor(HexColor(fill))
        if stroke:
            c.setStrokeColor(HexColor(stroke))
            c.setLineWidth(width)
        c.circle(cx, cy, r, stroke=int(bool(stroke)), fill=int(bool(fill)))

    def polyline(self, points: Sequence[tuple[float, float]], width: float, color: str, *,
                 closed: bool = False, fill: str | None = None):
        if len(points) < 2:
            return
        c = self.c
        c.setStrokeColor(HexColor(color))
        c.setLineWidth(width)
        if fill:
            c.setFillColor(HexColor(fill))
        path = c.beginPath()
        path.moveTo(*points[0])
        for pt in points[1:]:
            path.lineTo(*pt)
        if closed:
            path.close()
        c.drawPath(path, stroke=1, fill=int(bool(fill)))

    def rings(self, rings: Iterable[Sequence[tuple[float, float]]], *, fill: bool = False):
        """Closed rings as one path, in the current line style (set it first: `dash`, stroke colour, width)."""
        c = self.c
        path = c.beginPath()
        for ring in rings:
            path.moveTo(*ring[0])
            for pt in ring[1:]:
                path.lineTo(*pt)
            path.close()
        c.drawPath(path, stroke=1, fill=int(fill))

    def dash(self, line_style: str, width: float, gap: float, dash: float = 0.0):
        """Round-capped dotted or dashed lines (solid for anything else). Round caps add half a
        line width at each end of every dash; the pattern leaves that out."""
        c = self.c
        c.setLineCap(1)  # round: zero-length dashes become dots
        c.setLineJoin(1)
        if line_style == "dotted":
            c.setDash([0.01, gap + width])
        elif line_style == "dashed":
            c.setDash([max(dash - width, 0.01), gap + width])
        else:
            c.setDash([])


def draw_strokes(p: Painter, strokes):
    """Pen strokes (vectorize.Stroke) as round-capped polylines, in layer order, so a PDF
    export shows them the way the tablet draws them (but fixed, not movable)."""
    c = p.c
    c.setLineCap(1)
    c.setLineJoin(1)
    for s in strokes:
        if not s.points:
            continue
        c.setStrokeColor(HexColor(STROKE_COLORS.get(s.color.name, "#000000")))
        c.setLineWidth(s.width)
        path = c.beginPath()
        path.moveTo(*s.points[0])
        for pt in s.points[1:] or s.points:  # a single point still draws a dot
            path.lineTo(*pt)
        c.drawPath(path, stroke=1, fill=0)
