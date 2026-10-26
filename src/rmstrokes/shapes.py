"""Primitive shapes (circle, star, pin, tag, arrow, ...) as regions, and regions as pen strokes.

Shapes are defined in a unit box (0..1, y down) and scaled to the size asked for. Any region
(shapely polygon) becomes strokes in one of the fill styles:

  outline     one contour line just inside the edge
  filled      solid black ink (contour plus a scanline hatch)
  grey        the same in the grey pen
  white-fill  an outline over opaque white ink, so drawings underneath don't show through
"""
from __future__ import annotations

import math
from functools import cache

from rmscene import scene_items as si
from shapely import affinity
from shapely.geometry import Point, Polygon, box
from shapely.ops import unary_union

from .vectorize import HATCH_SPACING, Stroke, contours, hatch, resample, solid_fill

SHAPES = ("circle", "square", "rounded", "diamond", "star", "heart", "pin", "tag", "arrow")
FILL_STYLES = ("outline", "filled", "grey", "white-fill")
# Height / width each shape is drawn at unless asked otherwise.
ASPECT = {"tag": 0.62, "arrow": 0.6}


def _star(points: int = 5, inner: float = 0.42):
    pts = []
    for i in range(2 * points):
        r = 0.5 if i % 2 == 0 else 0.5 * inner
        a = math.radians(-90 + 180 * i / points)
        pts.append((0.5 + r * math.cos(a), 0.53 + r * math.sin(a)))
    return Polygon(pts)


@cache
def unit_shape(kind: str):
    """The shape in a unit box, y down."""
    if kind == "circle":
        return Point(0.5, 0.5).buffer(0.5, 64)
    if kind == "square":
        return box(0, 0, 1, 1)
    if kind == "rounded":
        return box(0.15, 0.15, 0.85, 0.85).buffer(0.15, 16)
    if kind == "diamond":
        return Polygon([(0.5, 0), (1, 0.5), (0.5, 1), (0, 0.5)])
    if kind == "star":
        return _star()
    if kind == "heart":
        return unary_union([Point(0.28, 0.3).buffer(0.25, 32), Point(0.72, 0.3).buffer(0.25, 32),
                            Polygon([(0.05, 0.4), (0.5, 0.97), (0.95, 0.4), (0.5, 0.25)])])
    if kind == "pin":
        head = Point(0.5, 0.36).buffer(0.36, 48)
        return unary_union([head, Polygon([(0.2, 0.56), (0.5, 1), (0.8, 0.56)])])
    if kind == "tag":
        body = Polygon([(0, 0.5), (0.26, 0), (1, 0), (1, 1), (0.26, 1)])
        return body.difference(Point(0.2, 0.5).buffer(0.08, 24))
    if kind == "arrow":
        return Polygon([(0, 0.32), (0.58, 0.32), (0.58, 0.04), (1, 0.5), (0.58, 0.96), (0.58, 0.68),
                        (0, 0.68)])
    raise ValueError(f"unknown shape {kind!r}; choose one of {', '.join(SHAPES)}")


def shape_region(kind: str, w: float, h: float | None = None, x: float = 0.0, y: float = 0.0):
    """The shape scaled to w x h px with its box's corner at (x, y). `h` defaults to the
    shape's own aspect (round shapes stay round)."""
    h = w * ASPECT.get(kind, 1.0) if h is None else h
    return affinity.affine_transform(unit_shape(kind), [w, 0, 0, h, x, y])


def region_strokes(region, style: str, pen: float, step: float = 2.0) -> list[Stroke]:
    """Pen strokes for a region in one of the FILL_STYLES."""
    if style == "outline":
        return [Stroke(tuple(resample(r, step)), pen) for r in contours(region.buffer(-pen / 2))]
    if style in ("filled", "grey"):
        color = si.PenColor.BLACK if style == "filled" else si.PenColor.GRAY
        return solid_fill(region, pen, color, step)
    if style == "white-fill":
        inner = region.buffer(-pen)
        white = [Stroke(tuple(resample(ch, step)), pen, si.PenColor.WHITE)
                 for ch in hatch(inner, pen * HATCH_SPACING)]
        return white + region_strokes(region, "outline", pen, step)
    raise ValueError(f"unknown fill style {style!r}; choose one of {', '.join(FILL_STYLES)}")
