"""Fonts: lookup, registration with reportlab, metrics and text widths.

Fonts are found by name (`<name>.ttf`) in the folders that registered font sources return
(`add_font_source`: a project's own font folder, say), then in the folders of installed font
packages, then in the fonts bundled with this package (rmstrokes/fonts/: Atkinson Hyperlegible Next
Regular, Italic and SemiBold, SIL OFL 1.1).

A font package is any installed package that names a callable returning its font folders in the
`rmstrokes.fonts` entry point group (its pyproject.toml):

    [project.entry-points."rmstrokes.fonts"]
    myfonts = "myfonts:font_dirs"
"""
from __future__ import annotations

import struct
from dataclasses import dataclass
from functools import cache
from importlib import metadata
from pathlib import Path
from typing import Callable, Iterable

from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont

BUNDLED_FONTS = Path(__file__).resolve().parent / "fonts"
ENTRY_POINT_GROUP = "rmstrokes.fonts"

_sources: list[Callable[[], Iterable[Path]]] = []


@dataclass(frozen=True)
class FontMetrics:
    cap_height: float  # fractions of the em
    x_height: float


def add_font_source(source: Callable[[], Iterable[Path]]) -> None:
    """Search the folders `source()` returns (called on every lookup) before the bundled fonts."""
    if source not in _sources:
        _sources.append(source)
    font.cache_clear()


@cache
def _installed_sources() -> tuple[Callable[[], Iterable[Path]], ...]:
    """The font packages' sources (entry point group rmstrokes.fonts), loaded once, by name."""
    eps = sorted(metadata.entry_points(group=ENTRY_POINT_GROUP), key=lambda ep: ep.name)
    return tuple(ep.load() for ep in eps)


def font_dirs() -> list[Path]:
    return [*(Path(d) for src in (*_sources, *_installed_sources()) for d in src()), BUNDLED_FONTS]


def font_path(name: str) -> Path:
    """`<name>.ttf` from the registered font folders, the font packages, else the bundled fonts."""
    dirs = font_dirs()
    for d in dirs:
        if (d / f"{name}.ttf").is_file():
            return d / f"{name}.ttf"
    raise ValueError(f"font {name!r} not found in: {', '.join(map(str, dirs))}")


def has_font(name: str) -> bool:
    """Whether `<name>.ttf` is in any font folder."""
    return any((d / f"{name}.ttf").is_file() for d in font_dirs())


@cache
def font(name: str) -> FontMetrics:
    """Register a TTF with reportlab (embedded as a subset) and return its metrics."""
    path = font_path(name)
    ttf = TTFont(name, str(path))
    pdfmetrics.registerFont(ttf)
    face = ttf.face
    os2 = face.get_table("OS/2")
    version = struct.unpack(">H", os2[:2])[0]
    x_height = struct.unpack(">h", os2[86:88])[0] if version >= 2 else 0.66 * face.capHeight
    return FontMetrics(face.capHeight / 1000, x_height / face.unitsPerEm)


def text_width(s: str, font_name: str, size: float) -> float:
    font(font_name)
    return pdfmetrics.stringWidth(s, font_name, size)


def missing_glyphs(s: str, font_name: str) -> set[str]:
    """Characters of `s` the font has no glyph for (they would print as blank boxes)."""
    font(font_name)
    cmap = pdfmetrics.getFont(font_name).face.charToGlyph
    return {c for c in s if not c.isspace() and ord(c) not in cmap}
