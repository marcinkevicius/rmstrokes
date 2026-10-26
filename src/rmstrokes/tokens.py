"""Tokens: small movable objects drawn as one compact cluster of pen strokes.

A token is a shape (a primitive from shapes.py or an SVG), optionally with an icon, a label or a
number inside, and optionally a blank **name tag** attached to it. Everything is drawn on the same
layer, in one contiguous run of strokes, with the tag touching the shape. So a single lasso around
the token takes the shape, its tag and whatever has been written in the tag, and moves them
together (write the name with the pen on the token's layer).

    art = token_art(Token("circle", size_mm=10, number=7, name_tag=NameTag()), device)
    strokes = art.placed(cx, cy)          # page px, centred on (cx, cy)

Token art is computed once per (token, device) in token-local px and moved per placement.
"""
from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from rmscene import scene_items as si
from shapely import affinity
from shapely.geometry import LineString, box
from shapely.ops import unary_union

from . import strokefont
from .devices import Device
from .geometry import Rect, rotate_point
from .shapes import FILL_STYLES, SHAPES, region_strokes, shape_region
from .vectorize import HATCH_SPACING, Stroke, art_strokes, contours, hatch, lines, load_art, resample
from .vectorize import STYLES as SVG_STYLES

TAG_SIDES = ("below", "right")
TAG_STYLES = ("box", "line")
# Where text sits inside each shape (fractions of its box) and how tall it may be (of the smaller
# side); shapes with a point or a hole keep their text in the roomy part.
TEXT_CENTRE = {"pin": (0.5, 0.36), "tag": (0.6, 0.5), "star": (0.5, 0.56), "arrow": (0.4, 0.5),
               "heart": (0.5, 0.42)}
TEXT_SCALE = {"star": 0.28, "pin": 0.32, "heart": 0.32, "diamond": 0.3, "arrow": 0.3, "tag": 0.42}


@dataclass(frozen=True)
class NameTag:
    """A blank tag to write a name in, attached below or to the right of the shape."""

    width_mm: float = 20.0
    height_mm: float = 7.0
    side: str = "below"
    style: str = "box"        # a rounded box, or just a line to write on
    overlap_mm: float = 0.8   # how far the tag reaches under the shape's edge: the two touch
    # Fill the tag with opaque white ink, so ruled lines or a grid under the token don't run
    # through the name (the white moves with the token; a printed knock-out wouldn't).
    knockout: bool = False

    def __post_init__(self):
        if self.side not in TAG_SIDES:
            raise ValueError(f"name tag side must be one of {', '.join(TAG_SIDES)}, not {self.side!r}")
        if self.style not in TAG_STYLES:
            raise ValueError(f"name tag style must be one of {', '.join(TAG_STYLES)}, not {self.style!r}")
        if self.width_mm <= 0 or self.height_mm <= 0:
            raise ValueError("a name tag needs a positive width and height")


@dataclass(frozen=True)
class Token:
    shape: str = "circle"        # a shapes.SHAPES name, or the path of an SVG
    size_mm: float = 10.0        # width of the shape
    height_mm: float | None = None  # default: the shape's own aspect
    style: str = "outline"       # shapes.FILL_STYLES (SVG: filled, white-fill, outline)
    pen_mm: float = 0.3
    label: str = ""              # text inside the shape, in the stroke font
    number: int | None = None    # shown when there is no label
    icon: str | None = None      # path of an SVG drawn inside the shape
    name_tag: NameTag | None = None
    svg_units: float | None = None  # SVG user units across size_mm (default: the SVG's width)

    @property
    def is_svg(self) -> bool:
        return self.shape not in SHAPES

    @property
    def text(self) -> str:
        return self.label or ("" if self.number is None else str(self.number))

    def check(self):
        if self.is_svg:
            if not Path(self.shape).is_file():
                raise ValueError(f"token shape {self.shape!r} is neither one of {', '.join(SHAPES)} "
                                 "nor an SVG file")
            if self.style not in SVG_STYLES:
                raise ValueError(f"an SVG token's style must be one of {', '.join(SVG_STYLES)}")
        elif self.style not in FILL_STYLES:
            raise ValueError(f"token style must be one of {', '.join(FILL_STYLES)}, not {self.style!r}")
        if self.size_mm <= 0:
            raise ValueError("token size must be positive")
        if bad := strokefont.missing_glyphs(self.text):
            raise ValueError(f"token label {self.text!r}: the stroke font has no {' '.join(sorted(bad))}")
        if self.icon and not Path(self.icon).is_file():
            raise ValueError(f"token icon {self.icon!r} is not a file")


@dataclass(frozen=True)
class TokenArt:
    """A token's strokes in token-local px, its footprint's bounding box at (0, 0)."""

    strokes: tuple[Stroke, ...]
    shape: Rect          # the shape's box
    tag: Rect | None     # the name tag's box
    footprint: object    # shapely region: shape plus tag (for dotted outlines)

    @property
    def width(self) -> float:
        return self.footprint.bounds[2]

    @property
    def height(self) -> float:
        return self.footprint.bounds[3]

    def placed(self, cx: float, cy: float, rotation: float = 0.0) -> list[Stroke]:
        """The strokes with the footprint's box centred on (cx, cy), turned `rotation` degrees
        clockwise about that centre."""
        dx, dy = cx - self.width / 2, cy - self.height / 2
        if not rotation:
            return [s.map(lambda x, y: (x + dx, y + dy)) for s in self.strokes]
        return [s.map(lambda x, y: rotate_point(x + dx, y + dy, cx, cy, rotation)) for s in self.strokes]

    def outline(self, cx: float = 0.0, cy: float = 0.0, rotation: float = 0.0):
        """The footprint as a region, placed like `placed`."""
        g = affinity.translate(self.footprint, cx - self.width / 2, cy - self.height / 2)
        return affinity.rotate(g, rotation, origin=(cx, cy)) if rotation else g


@dataclass(frozen=True)
class Placement:
    """A token as placed on a page: its art centred in `box` (page px), turned `rotation` degrees,
    on `layer`. Templates may list them in `Page.meta["placements"]` (and the boxes their
    background is laid out in, as (label, Rect), in `Page.meta["areas"]`), so `rmstrokes explain`
    can show how the page was built; nothing else reads them."""

    layer: str
    token: Token
    art: TokenArt
    box: Rect
    rotation: float = 0.0

    def strokes(self) -> list[Stroke]:
        return self.art.placed(*self.box.center, self.rotation)


def _shape(token: Token, device: Device, pen: float, step: float):
    w = device.mm(token.size_mm)
    if token.is_svg:
        art = load_art(Path(token.shape), w, token.svg_units, step)
        region = unary_union([art.dark, art.light])
        return region, art_strokes(art, token.style, step)
    h = device.mm(token.height_mm) if token.height_mm else None
    region = shape_region(token.shape, w, h)
    return region, region_strokes(region, token.style, pen, step)


def _inside(token: Token, device: Device, region, pen: float, step: float) -> list[Stroke]:
    """Icon and text, centred in the shape's roomy part."""
    minx, miny, maxx, maxy = region.bounds
    w, h = maxx - minx, maxy - miny
    fx, fy = TEXT_CENTRE.get(token.shape, (0.5, 0.5))
    cx, cy = minx + fx * w, miny + fy * h
    on_ink = token.style == "filled"
    color = si.PenColor.WHITE if on_ink else si.PenColor.BLACK
    out: list[Stroke] = []
    if token.icon:
        side = min(w, h) * 0.56
        art = load_art(Path(token.icon), side, None, step)
        ax0, ay0, ax1, ay1 = unary_union([art.dark, art.light]).bounds
        ox, oy = cx - (ax0 + ax1) / 2, cy - (ay0 + ay1) / 2
        out += [Stroke(tuple((x + ox, y + oy) for x, y in s.points), s.width, color, s.tool)
                for s in art_strokes(art, "filled", step) if s.color != si.PenColor.WHITE]
    if token.text:
        th = min(w, h) * TEXT_SCALE.get(token.shape, 0.45)
        th = min(th, w * 0.66 / max(strokefont.text_width(token.text, 1.0), 1e-6))
        text_pen = max(pen, th * 0.11)
        out += strokefont.text_strokes(token.text, cx, cy, th, text_pen, color=color, step=step)
    return out


def _tag(tag: NameTag, device: Device, region, pen: float, step: float) -> tuple[list[Stroke], Rect]:
    minx, miny, maxx, maxy = region.bounds
    tw, th, overlap = device.mm(tag.width_mm), device.mm(tag.height_mm), device.mm(tag.overlap_mm)
    if tag.side == "below":
        r = Rect((minx + maxx) / 2 - tw / 2, maxy - overlap, tw, th)
    else:
        r = Rect(maxx - overlap, (miny + maxy) / 2 - th / 2, tw, th)
    keep_out = region.buffer(pen * 0.6)
    shape = box(r.x, r.y, r.right, r.bottom)
    if tag.style == "box":
        shape = shape.buffer(-device.mm(1)).buffer(device.mm(1))
        rings = [LineString(ring) for ring in contours(shape.buffer(-pen / 2))]
    else:  # a line to write on, with short ends rising at both sides
        y = r.bottom - pen / 2
        rise = min(device.mm(1.2), th / 3)
        rings = [LineString([(r.x + pen, y - rise), (r.x + pen, y), (r.right - pen, y),
                             (r.right - pen, y - rise)])]
    strokes = []
    if tag.knockout:  # white first, so the outline is drawn over its edge
        white = shape.buffer(-pen * 0.5).difference(region.buffer(pen * 0.5))
        strokes += [Stroke(tuple(resample(ch, step)), pen, si.PenColor.WHITE)
                    for ch in hatch(white, pen * HATCH_SPACING)]
    for ring in rings:
        for part in lines(ring.difference(keep_out)):  # the tag runs behind the shape, not through it
            if part.length >= pen:
                strokes.append(Stroke(tuple(resample(list(part.coords), step)), pen))
    return strokes, r


@lru_cache(maxsize=256)
def token_art(token: Token, device: Device, step: float = 2.0) -> TokenArt:
    token.check()
    pen = device.mm(token.pen_mm)
    region, strokes = _shape(token, device, pen, step)
    strokes = list(strokes) + _inside(token, device, region, pen, step)
    tag_rect = None
    footprint = region
    if token.name_tag:
        tag_strokes, tag_rect = _tag(token.name_tag, device, region, pen, step)
        strokes += tag_strokes  # last, so the cluster stays one run: shape, inside, tag
        footprint = unary_union([region, box(tag_rect.x, tag_rect.y, tag_rect.right, tag_rect.bottom)])
    minx, miny, _, _ = footprint.bounds
    strokes = [s.map(lambda x, y: (x - minx, y - miny)) for s in strokes]
    sx0, sy0, sx1, sy1 = region.bounds
    return TokenArt(tuple(strokes), Rect(sx0 - minx, sy0 - miny, sx1 - sx0, sy1 - sy0),
                    tag_rect.moved(-minx, -miny) if tag_rect else None,
                    affinity.translate(footprint, -minx, -miny))
