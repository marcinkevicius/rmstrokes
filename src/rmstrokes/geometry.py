"""Page geometry shared by the PDF background and the pen strokes.

Two coordinate systems:

- **page px**: origin at the top-left corner of the page as shown, y down, in device pixels. The
  PDF renderer uses these (mapped to PDF points at ``Device.pt_per_px``), and so do strokes.
- **.rm coordinates**: what v6 ``.rm`` stroke points use. Same scale and y axis, but **x = 0 is the
  horizontal centre** of the page (rm.py converts).
"""
from __future__ import annotations

import math
from dataclasses import dataclass

from .devices import Device


@dataclass(frozen=True)
class Rect:
    x: float
    y: float
    w: float
    h: float

    @property
    def right(self) -> float:
        return self.x + self.w

    @property
    def bottom(self) -> float:
        return self.y + self.h

    @property
    def center(self) -> tuple[float, float]:
        return self.x + self.w / 2, self.y + self.h / 2

    def inset(self, d: float) -> Rect:
        return Rect(self.x + d, self.y + d, self.w - 2 * d, self.h - 2 * d)

    def contains(self, x: float, y: float) -> bool:
        return self.x <= x < self.right and self.y <= y < self.bottom

    def moved(self, dx: float, dy: float) -> Rect:
        return Rect(self.x + dx, self.y + dy, self.w, self.h)

    def union(self, other: Rect) -> Rect:
        x, y = min(self.x, other.x), min(self.y, other.y)
        return Rect(x, y, max(self.right, other.right) - x, max(self.bottom, other.bottom) - y)

    @classmethod
    def around(cls, cx: float, cy: float, w: float, h: float) -> Rect:
        return cls(cx - w / 2, cy - h / 2, w, h)

    @classmethod
    def bounds(cls, points) -> Rect:
        xs = [p[0] for p in points]
        ys = [p[1] for p in points]
        return cls(min(xs), min(ys), max(xs) - min(xs), max(ys) - min(ys))


class FitError(ValueError):
    """Cells that don't fit their area."""


def grid_cells(area: Rect, count: int, cell_w: float, cell_h: float, gap: float = 0.0,
               columns: int | None = None) -> list[Rect]:
    """`count` cells of cell_w x cell_h in rows across `area` (as many columns as fit, or
    `columns`), `gap` apart, the block centred in the area and a last, shorter row centred too.
    Raises FitError if they don't fit."""
    if count < 1:
        raise FitError("a grid needs at least one cell")
    fit = max(1, int((area.w + gap) // (cell_w + gap)))
    cols = min(columns or fit, count)
    rows = -(-count // cols)
    if cols * cell_w + (cols - 1) * gap > area.w + 1e-6 or rows * cell_h + (rows - 1) * gap > area.h + 1e-6:
        raise FitError(f"{count} cells of {cell_w:.0f} x {cell_h:.0f} px don't fit in "
                       f"{area.w:.0f} x {area.h:.0f} px")
    y = area.y + (area.h - rows * cell_h - (rows - 1) * gap) / 2
    cells = []
    for row in range(rows):
        n = min(cols, count - row * cols)
        x = area.x + (area.w - n * cell_w - (n - 1) * gap) / 2
        for _ in range(n):
            cells.append(Rect(x, y, cell_w, cell_h))
            x += cell_w + gap
        y += cell_h + gap
    return cells


def page_size(device: Device, landscape: bool = False) -> tuple[int, int]:
    """(width, height) of the page as shown, in device px."""
    return (device.height, device.width) if landscape else (device.width, device.height)


def to_rm(device: Device, x: float, y: float) -> tuple[float, float]:
    """Page px -> .rm coordinates (portrait page)."""
    return x - device.width / 2, y


def from_rm(device: Device, x: float, y: float) -> tuple[float, float]:
    """.rm coordinates -> page px (portrait page)."""
    return x + device.width / 2, y


def rm_rect(device: Device, r: Rect) -> Rect:
    """Page px rect -> the same rect in .rm coordinates."""
    x, y = to_rm(device, r.x, r.y)
    return Rect(x, y, r.w, r.h)


def rotate_point(x: float, y: float, cx: float, cy: float, degrees: float) -> tuple[float, float]:
    """Turn (x, y) about (cx, cy) by `degrees` clockwise as seen on the page (y points down)."""
    if degrees % 360 == 180:  # exact, so a half turn maps a grid onto itself
        return 2 * cx - x, 2 * cy - y
    a = math.radians(degrees)
    dx, dy = x - cx, y - cy
    return cx + dx * math.cos(a) - dy * math.sin(a), cy + dx * math.sin(a) + dy * math.cos(a)
