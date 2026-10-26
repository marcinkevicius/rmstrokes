"""A single-line stroke font: text as pen strokes, so a label moves with the token it is on.

Glyphs are polylines on a 4 wide, 6 tall grid (y down), drawn the way a careful hand writes
capitals and digits. Lower case is set as capitals. ``text_strokes`` lays a line of text out
centred on a point; ``missing_glyphs`` lists characters the font can't draw.
"""
from __future__ import annotations

import math

from rmscene import scene_items as si

from .vectorize import Stroke, resample

GLYPH_W, GLYPH_H = 4.0, 6.0
ADVANCE = 5.6  # glyph width plus the gap to the next one, in grid units


def _ellipse(cx, cy, rx, ry, a0=0.0, a1=360.0, n=24):
    return [(cx + rx * math.cos(math.radians(a)), cy + ry * math.sin(math.radians(a)))
            for a in (a0 + (a1 - a0) * i / n for i in range(n + 1))]


def _dot(x, y):
    return [(x, y), (x + 0.01, y)]


GLYPHS: dict[str, list[list[tuple[float, float]]]] = {
    "A": [[(0, 6), (2, 0), (4, 6)], [(0.7, 4), (3.3, 4)]],
    "B": [[(0, 3), (0, 0), (2.4, 0), *_ellipse(2.4, 1.5, 1.4, 1.5, 270, 450, 10)[1:], (0, 3)],
          [(0, 3), (2.5, 3), *_ellipse(2.5, 4.5, 1.5, 1.5, 270, 450, 10)[1:], (0, 6), (0, 3)]],
    "C": [_ellipse(2, 3, 2, 3, 320, 40, 20)],
    "D": [[(0, 0), (0, 6), (1.6, 6), *_ellipse(1.6, 3, 2.4, 3, 90, -90, 16)[1:], (0, 0)]],
    "E": [[(4, 0), (0, 0), (0, 6), (4, 6)], [(0, 3), (3, 3)]],
    "F": [[(4, 0), (0, 0), (0, 6)], [(0, 3), (3, 3)]],
    "G": [[*_ellipse(2, 3, 2, 3, 320, 0, 22), (2.2, 3)]],
    "H": [[(0, 0), (0, 6)], [(4, 0), (4, 6)], [(0, 3), (4, 3)]],
    "I": [[(2, 0), (2, 6)], [(1, 0), (3, 0)], [(1, 6), (3, 6)]],
    "J": [[(4, 0), (4, 4.4), *_ellipse(2, 4.4, 2, 1.6, 0, 180, 12)[1:]]],
    "K": [[(0, 0), (0, 6)], [(4, 0), (0, 3.8)], [(1.4, 2.5), (4, 6)]],
    "L": [[(0, 0), (0, 6), (4, 6)]],
    "M": [[(0, 6), (0, 0), (2, 3.5), (4, 0), (4, 6)]],
    "N": [[(0, 6), (0, 0), (4, 6), (4, 0)]],
    "O": [_ellipse(2, 3, 2, 3)],
    "P": [[(0, 6), (0, 0), (2.4, 0), *_ellipse(2.4, 1.6, 1.6, 1.6, 270, 450, 12)[1:], (0, 3.2)]],
    "Q": [_ellipse(2, 3, 2, 3), [(2.4, 4.4), (4.2, 6.4)]],
    "R": [[(0, 6), (0, 0), (2.4, 0), *_ellipse(2.4, 1.6, 1.6, 1.6, 270, 450, 12)[1:], (0, 3.2)],
          [(1.8, 3.2), (4, 6)]],
    "S": [[*_ellipse(2, 1.5, 1.9, 1.5, 340, 90, 12), *_ellipse(2, 4.5, 2, 1.5, 270, 520, 14)[1:]]],
    "T": [[(0, 0), (4, 0)], [(2, 0), (2, 6)]],
    "U": [[(0, 0), (0, 4), *_ellipse(2, 4, 2, 2, 180, 0, 12)[1:], (4, 0)]],
    "V": [[(0, 0), (2, 6), (4, 0)]],
    "W": [[(0, 0), (1, 6), (2, 2.5), (3, 6), (4, 0)]],
    "X": [[(0, 0), (4, 6)], [(4, 0), (0, 6)]],
    "Y": [[(0, 0), (2, 3), (4, 0)], [(2, 3), (2, 6)]],
    "Z": [[(0, 0), (4, 0), (0, 6), (4, 6)]],
    "0": [_ellipse(2, 3, 1.7, 3)],
    "1": [[(0.8, 1.2), (2.2, 0), (2.2, 6)], [(0.8, 6), (3.6, 6)]],
    "9": [_ellipse(2, 1.9, 2, 1.9), [(4, 1.9), (4, 4.2), *_ellipse(2, 4.2, 2, 1.8, 0, 150, 10)[1:]]],
    "8": [_ellipse(2, 1.45, 1.7, 1.45), _ellipse(2, 4.35, 2, 1.65)],
    "7": [[(0, 0), (4, 0), (1.4, 6)]],
    "6": [[*_ellipse(2, 1.8, 2, 1.8, 330, 180, 10), (0, 4.3)], _ellipse(2, 4.3, 2, 1.7)],
    "5": [[(3.8, 0), (0.4, 0), (0.1, 2.8)],
          [(0.1, 2.8), *_ellipse(1.9, 4.1, 2.1, 1.9, 235, 495, 16)[1:]]],
    "4": [[(3, 6), (3, 0), (0, 4.2), (4, 4.2)]],
    "3": [[*_ellipse(2, 1.45, 1.8, 1.45, 200, 450, 12)],
          [*_ellipse(2, 4.4, 2, 1.6, 270, 520, 12)]],
    "2": [[*_ellipse(2, 1.8, 1.9, 1.8, 190, 380, 12), (0, 6), (4, 6)]],
    "-": [[(0.8, 3), (3.2, 3)]],
    "+": [[(0.6, 3), (3.4, 3)], [(2, 1.6), (2, 4.4)]],
    ".": [_dot(2, 5.9)],
    ",": [[(2.2, 5.5), (1.6, 6.8)]],
    "!": [[(2, 0), (2, 4.2)], _dot(2, 5.9)],
    "?": [[*_ellipse(2, 1.6, 1.9, 1.6, 190, 450, 12), (2, 4.2)], _dot(2, 5.9)],
    "'": [[(2, 0), (2, 1.4)]],
    ":": [_dot(2, 1.9), _dot(2, 5.9)],
    "/": [[(0.4, 6), (3.6, 0)]],
    "#": [[(0, 2), (4, 2)], [(0, 4), (4, 4)], [(1.4, 0.6), (1.4, 5.4)], [(2.6, 0.6), (2.6, 5.4)]],
    "(": [_ellipse(3.4, 3, 2, 3.3, 235, 125, 12)],
    ")": [_ellipse(0.6, 3, 2, 3.3, -55, 55, 12)],
    " ": [],
}


def missing_glyphs(text: str) -> set[str]:
    return {c for c in text.upper() if c not in GLYPHS}


def text_width(text: str, height: float) -> float:
    """Width in px of `text` set `height` px tall (cap height)."""
    if not text:
        return 0.0
    k = height / GLYPH_H
    return ((len(text) - 1) * ADVANCE + GLYPH_W) * k


def glyph_strokes(ch: str, x: float, y: float, height: float, pen: float, *,
                  color: si.PenColor = si.PenColor.BLACK, step: float = 2.0) -> list[Stroke]:
    """One glyph with its top-left grid corner at (x, y), `height` px tall."""
    k = height / GLYPH_H
    return [Stroke(tuple(resample([(x + px * k, y + py * k) for px, py in line], step)), pen, color)
            for line in GLYPHS[ch.upper()]]


def text_strokes(text: str, cx: float, cy: float, height: float, pen: float, *,
                 color: si.PenColor = si.PenColor.BLACK, step: float = 2.0) -> list[Stroke]:
    """`text` on one line, centred on (cx, cy), capitals `height` px tall."""
    if bad := missing_glyphs(text):
        raise ValueError(f"the stroke font has no {' '.join(sorted(bad))} (letters, digits and "
                         f"{''.join(c for c in GLYPHS if not c.isalnum() and c != ' ')} only)")
    k = height / GLYPH_H
    x = cx - text_width(text, height) / 2
    y = cy - height / 2
    out: list[Stroke] = []
    for ch in text:
        out += glyph_strokes(ch, x, y, height, pen, color=color, step=step)
        x += ADVANCE * k
    return out
