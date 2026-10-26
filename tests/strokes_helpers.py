"""Helpers for the rmstrokes tests (imported by name; conftest.py holds the fixtures)."""
import io
import math

from pypdf import PdfReader

from rmstrokes.rm import read_layers
from rmstrokes.rmdoc import read_rmdoc

# A small icon: a dark disc with a light hole, and a dark outlined square beside it.
ICON_SVG = """<svg xmlns="http://www.w3.org/2000/svg" width="40" height="40" viewBox="0 0 40 40">
  <circle cx="14" cy="20" r="10" fill="#000"/>
  <circle cx="14" cy="20" r="4" fill="#fff"/>
  <rect x="27" y="14" width="10" height="12" fill="#fff" stroke="#000" stroke-width="1.5"/>
</svg>
"""


def layers(path):
    """[(page id, [(layer name, line count), ...]), ...] of an .rmdoc."""
    doc = read_rmdoc(path)
    return [[(name, len(lines)) for name, lines in read_layers(rm)] for _, rm in doc.pages]


def pdf_text(pdf: bytes, page: int = 0) -> str:
    return PdfReader(io.BytesIO(pdf)).pages[page].extract_text()


def pdf_page_count(pdf: bytes) -> int:
    return len(PdfReader(io.BytesIO(pdf)).pages)


def bounds(strokes):
    xs = [x for s in strokes for x, _ in s.points]
    ys = [y for s in strokes for _, y in s.points]
    return min(xs), min(ys), max(xs), max(ys)


def dist(a, b):
    return math.dist(a, b)
