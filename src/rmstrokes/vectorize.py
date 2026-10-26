"""Turn an SVG drawing into reMarkable pen strokes.

1. Parse the SVG in paint order (svgelements) into
   - outline centrelines: every dark-stroked path, drawn as fineliner at its own width;
   - dark and light fill regions, composited with shapely (even-odd fill, later shapes
     cover earlier ones, strokes buffered to their width).
2. Fill regions become strokes:
   - a contour pass traces the region boundary, eroded by half a pen width, so the edge
     is one smooth line (this is what removes the scalloped edge seen where
     hatch lines ended against a light highlight inside a dark area);
   - a boustrophedon scanline hatch covers the inside, lines 0.8 pen widths apart, joined
     wherever the connector stays inside the shape.
3. Strokes are computed once per (drawing, box size, style) in box-local coordinates and
   translated/rotated per placement (Stroke.map).
"""
from __future__ import annotations

import math
from dataclasses import dataclass, replace
from functools import lru_cache
from pathlib import Path

import numpy as np
import svgelements as se
from rmscene import scene_items as si
from shapely import affinity
from shapely.geometry import LineString, MultiPolygon, Point, Polygon
from shapely.ops import unary_union

DEFAULT_STEP = 4.0  # max px between stroke points
HATCH_SPACING = 0.8  # hatch line distance, in pen widths
CONTOUR_SIMPLIFY = 0.15  # px; drops redundant points on contour rings


@dataclass(frozen=True)
class Stroke:
    points: tuple[tuple[float, float], ...]  # page (or box-local) pixels, y down
    width: float  # pixels
    color: si.PenColor = si.PenColor.BLACK
    tool: si.Pen = si.Pen.FINELINER_2

    def map(self, fn) -> Stroke:
        return replace(self, points=tuple(fn(x, y) for x, y in self.points))


@dataclass
class Art:
    """Composited regions of one SVG, in pixels for a box with its corner at (0, 0)."""
    dark: Polygon | MultiPolygon
    light: Polygon | MultiPolygon
    outlines: list[tuple[list[tuple[float, float]], float]]  # (centreline, width)
    pen: float  # main stroke width (most common outline width)


# --------------------------------------------------------------------------- helpers

def resample(pts, step):
    """Insert points so no segment is longer than `step` pixels (device-like density)."""
    pts = list(pts)
    out = [pts[0]]
    for (x0, y0), (x1, y1) in zip(pts, pts[1:]):
        n = max(1, int(math.ceil(math.hypot(x1 - x0, y1 - y0) / step)))
        out += [(x0 + (x1 - x0) * i / n, y0 + (y1 - y0) * i / n) for i in range(1, n + 1)]
    return out


def polygons(geom):
    if geom.is_empty:
        return []
    if isinstance(geom, Polygon):
        return [geom]
    return [g for g in getattr(geom, "geoms", []) if isinstance(g, Polygon) and not g.is_empty]


def lines(geom):
    if geom.is_empty:
        return []
    if isinstance(geom, LineString):
        return [geom]
    out = []
    for g in getattr(geom, "geoms", []):
        out += lines(g)
    return out


def _ring_coords(subpath: se.Path, step: float):
    """Sample a subpath every <= `step` px. (svgelements' exact length() is far too slow
    for this; a 16-point probe per curve segment is plenty to pick the sample count.)"""
    pts: list[tuple[float, float]] = []
    for seg in subpath:
        if isinstance(seg, se.Move):
            pts.append((float(seg.end.x), float(seg.end.y)))
        elif isinstance(seg, (se.Line, se.Close)):
            if seg.start is not None and seg.end is not None:
                pts += resample([(seg.start.x, seg.start.y), (seg.end.x, seg.end.y)], step)[1:]
        else:
            probe = seg.npoint(np.linspace(0, 1, 16))
            approx = float(np.sum(np.hypot(*np.diff(probe, axis=0).T)))
            n = max(2, int(math.ceil(approx / step)) + 1)
            pts += [(float(x), float(y)) for x, y in seg.npoint(np.linspace(0, 1, n))[1:]]
    out = [pts[0]] if pts else []
    for p in pts[1:]:
        if math.dist(p, out[-1]) > 1e-6:
            out.append(p)
    return out


def _dark(c) -> bool | None:
    """True for dark paint, False for light, None for no paint."""
    if c is None or c.value is None or c.alpha == 0:
        return None
    return (0.299 * c.red + 0.587 * c.green + 0.114 * c.blue) < 128


# --------------------------------------------------------------------------- SVG -> regions

def load_art(svg_path: Path, box: float, size: float | None = None, step: float = DEFAULT_STEP) -> Art:
    """Parse an SVG scaled so `size` user units (default: the SVG's width) span `box` px, with
    its corner at (0, 0)."""
    probe = se.SVG.parse(str(svg_path))
    k = box / float(size or probe.width or 45.0)
    svg = se.SVG.parse(str(svg_path), transform=f"scale({k})")
    dark = Polygon()
    light = Polygon()
    outlines: list[tuple[list[tuple[float, float]], float]] = []
    for el in svg.elements():
        if not isinstance(el, se.Shape) or isinstance(el, se.Text):
            continue
        path = se.Path(el)
        path.reify()
        subpaths, rings = [], []
        for sp in map(se.Path, path.as_subpaths()):
            r = _ring_coords(sp, step / 2)
            if len(r) >= 2:
                subpaths.append(sp)
                rings.append(r)
        if not subpaths:
            continue
        fill_rule_evenodd = (el.values.get("fill-rule", "nonzero") == "evenodd")
        fill = Polygon()
        for r in rings:
            if len(r) >= 3:
                p = Polygon(r).buffer(0)
                # Nonzero is approximated by union, which is right for the
                # non-self-intersecting outlines icon-style SVGs use.
                fill = fill.symmetric_difference(p) if fill_rule_evenodd else fill.union(p)
        stroke_geom = Polygon()
        stroke_dark = _dark(el.stroke) if el.stroke_width else None
        if stroke_dark is not None:
            w = float(el.stroke_width)
            cap = {"round": 1, "square": 3}.get(el.values.get("stroke-linecap"), 2)
            join = {"round": 1, "bevel": 3}.get(el.values.get("stroke-linejoin"), 2)
            centrelines = []
            for sp, r in zip(subpaths, rings):
                closed = isinstance(list(sp)[-1], se.Close)
                centrelines.append(r + [r[0]] if closed else r)
            stroke_geom = unary_union([
                LineString(c).buffer(w / 2, cap_style=cap, join_style=join, mitre_limit=4)
                for c in centrelines if len(c) >= 2])
            if stroke_dark:
                outlines += [(c, w) for c in centrelines if len(c) >= 2]
        # Composite in paint order: fill, then stroke; later shapes cover earlier ones.
        for geom, is_dark in ((fill, _dark(el.fill)), (stroke_geom, stroke_dark)):
            if geom.is_empty or is_dark is None:
                continue
            if is_dark:
                dark, light = dark.union(geom), light.difference(geom)
            else:
                light, dark = light.union(geom), dark.difference(geom)
    widths = [w for _, w in outlines]
    pen = max(set(widths), key=widths.count) if widths else 1.5 * k
    return Art(dark.buffer(0), light.buffer(0), outlines, pen)


# --------------------------------------------------------------------------- regions -> strokes

def hatch(region, spacing, angle=0.0):
    """Fill `region` with parallel scanlines, joined boustrophedon-style where the
    connector stays inside the region (fewer, longer strokes)."""
    if region.is_empty:
        return []
    c = region.centroid
    rot = affinity.rotate(region, -angle, origin=c)
    minx, miny, maxx, maxy = rot.bounds
    tol = region.buffer(spacing * 0.3)
    rows = []
    # Centre the scanlines vertically so both ends get the same margin.
    n = max(1, int(math.floor((maxy - miny) / spacing)) + 1)
    y = miny + ((maxy - miny) - (n - 1) * spacing) / 2
    for _ in range(n):
        cut = LineString([(minx - 1, y), (maxx + 1, y)]).intersection(rot)
        segs = [s for s in lines(cut) if s.length > 0.5]
        rows.append(sorted((affinity.rotate(s, angle, origin=c) for s in segs),
                           key=lambda s: s.bounds[0]))
        y += spacing

    chains, open_chains = [], []
    for row in rows:
        next_open = []
        for seg in row:
            a, b = seg.coords[0], seg.coords[-1]
            joined = False
            for ch in open_chains:
                end = ch[-1]
                start, stop = (a, b) if math.dist(end, a) <= math.dist(end, b) else (b, a)
                if math.dist(end, start) < spacing * 4 and tol.contains(LineString([end, start])):
                    ch += [start, stop]
                    open_chains.remove(ch)
                    next_open.append(ch)
                    joined = True
                    break
            if not joined:
                ch = [a, b]
                chains.append(ch)
                next_open.append(ch)
        open_chains = next_open
    return chains


def contours(region):
    """Boundary rings of a region (exterior and holes) as closed polylines."""
    out = []
    for poly in polygons(region):
        for ring in [poly.exterior, *poly.interiors]:
            ring = ring.simplify(CONTOUR_SIMPLIFY)
            pts = list(ring.coords)
            if len(pts) >= 3:
                out.append(pts)
    return out


def ink(strokes):
    """Area covered by strokes (round caps and joins)."""
    return unary_union([LineString(s.points).buffer(s.width / 2) if len(s.points) > 1
                        else Point(s.points[0]).buffer(s.width / 2) for s in strokes])


def opened(region, r):
    """Morphological opening: drops slivers thinner than 2r."""
    return region.buffer(-r).buffer(r)


def solid_fill(region, pen: float, color: si.PenColor, step: float) -> list[Stroke]:
    """Cover `region` with ink of width `pen`: one smooth contour line per boundary ring,
    half a pen in from the edge so the round ink edge lands on the region edge, plus a
    scanline hatch inside it. Parts thinner than the pen are left to `patch_thin`."""
    strokes: list[Stroke] = []
    # Opening drops hair-thin cores (a feature exactly one pen wide erodes to a sliver);
    # those parts are drawn by patch_thin instead.
    core = opened(region.buffer(-pen / 2), pen * 0.15)
    for ring in contours(core):
        strokes.append(Stroke(tuple(resample(ring, step)), pen, color))
    # The hatch overlaps the contour line by a quarter pen, so narrow spikes and corners
    # where the scanlines get short still close up.
    for ch in hatch(core.buffer(-pen * 0.25), pen * HATCH_SPACING):
        strokes.append(Stroke(tuple(resample(ch, step)), pen, color))
    return strokes


def patch_thin(region, strokes, pen: float, step: float, *, outlines=(), keep=None,
               color=si.PenColor.BLACK) -> list[Stroke]:
    """Strokes for the parts of `region` that `strokes` leave uncovered: features thinner
    than the pen, like a thin cross on top of a shape or the outer band of a dark shape
    between its light highlight line and the edge.

    First the SVG's own outline centrelines, where they run through a gap and stay inside
    `keep`. Then each remaining bit gets a contour line at its own thickness (a band's
    eroded core is a sliver along its middle), or a dot if it is tiny."""
    residual = opened(region.difference(ink(strokes)), pen * 0.08)
    out: list[Stroke] = []
    if keep is not None and not residual.is_empty:
        gaps = keep.intersection(residual.buffer(pen * 0.25))
        for c, w in outlines:
            for part in clip_outline(c, gaps):
                if part_len(part) >= w:
                    out.append(Stroke(tuple(resample(part, step)), w, color))
        if out:
            residual = opened(residual.difference(ink(out)), pen * 0.08)
    for bit in polygons(residual):
        if bit.area < (pen * 0.3) ** 2:
            continue
        t = min(pen, max(1.0, 2 * bit.area / bit.length))  # band thickness ~ 2A/P
        # Grow the bit into whatever it borders (inside the region) so its line overlaps
        # the neighbouring fill instead of leaving a seam where they meet.
        bit = bit.buffer(pen * 0.6).intersection(region)
        bit = max(polygons(bit), key=lambda g: g.area) if polygons(bit) else bit
        rings = contours(bit.buffer(-t * 0.4))
        for ring in rings:
            out.append(Stroke(tuple(resample(ring, step)), t * 0.9, color))
        if not rings:
            p = bit.representative_point()
            out.append(Stroke(((p.x, p.y), (p.x + 0.01, p.y)), t, color))
    return out


def part_len(points) -> float:
    return sum(math.dist(a, b) for a, b in zip(points, points[1:]))


def clip_outline(points, keep):
    """Parts of a centreline inside `keep`, as polylines."""
    if keep.is_empty:
        return []
    geom = LineString(points).intersection(keep)
    return [list(l.coords) for l in lines(geom) if l.length > 0.5]


STYLES = ("filled", "white-fill", "outline")


@lru_cache(maxsize=256)
def svg_strokes_local(svg_path: str, box: float, size: float | None, style: str,
                        step: float = DEFAULT_STEP) -> tuple[Stroke, ...]:
    """Strokes for one SVG in a box with its top-left corner at (0, 0), in paint
    order (later strokes draw on top).

    style:
      "filled"     dark areas as solid ink, light areas left as paper
      "white-fill" outline over an opaque white-ink fill (hides what is underneath)
      "outline"    outline and dark details only, no white ink
    """
    if style not in STYLES:
        raise ValueError(f"unknown style {style!r}; choose one of {', '.join(STYLES)}")
    return tuple(art_strokes(load_art(Path(svg_path), box, size, step), style, step))


def art_strokes(art: Art, style: str, step: float = DEFAULT_STEP, *,
                min_pen: float = 0.0) -> list[Stroke]:
    """Strokes for composited art (see svg_strokes_local for the styles).
    `min_pen` thickens the pen and every outline, for small copies whose scaled lines
    would be too thin to see on e-ink."""
    if min_pen:
        art = Art(art.dark, art.light, [(c, max(w, min_pen)) for c, w in art.outlines],
                       max(art.pen, min_pen))
    pen = art.pen
    strokes: list[Stroke] = []
    if style == "filled":
        # The dark region already includes the outline bands, so its contour line *is* the
        # outline, and light highlights inside it stay paper-white with smooth edges.
        strokes += solid_fill(art.dark, pen, si.PenColor.BLACK, step)
        # Outline centrelines may only fill gaps well clear of the light highlights.
        keep = art.dark.buffer(-pen * 0.2).difference(art.light.buffer(pen * 0.5))
        strokes += patch_thin(art.dark, strokes, pen, step, outlines=art.outlines, keep=keep)
        return strokes

    outline = [Stroke(tuple(resample(c, step)), w) for c, w in art.outlines]
    band = ink(outline) if outline else Polygon()
    if style == "white-fill":
        # Opaque white ink under the outline, so a grey background doesn't show through.
        # Its edge is hidden under the outline, so plain hatching is enough.
        interior = art.light.difference(band).buffer(-pen * 0.45)
        for ch in hatch(interior, pen * HATCH_SPACING):
            strokes.append(Stroke(tuple(resample(ch, step)), pen, si.PenColor.WHITE))
    # Dark details the outline doesn't cover (an eye drawn as a filled dot, say).
    details = opened(art.dark.difference(band), pen * 0.25)
    strokes += solid_fill(details.buffer(pen * 0.15).intersection(art.dark), pen, si.PenColor.BLACK, step)
    strokes += outline
    return strokes


def coverage(strokes, region) -> tuple[float, float]:
    """(fraction of `region` covered by the strokes, area drawn outside it / region area)."""
    if region.area == 0:
        return 1.0, 0.0
    covered = ink(strokes)
    return covered.intersection(region).area / region.area, covered.difference(region).area / region.area
