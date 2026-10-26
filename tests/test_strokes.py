"""SVG and primitive shapes to strokes, and the stroke font."""
import pytest
from rmscene import scene_items as si
from shapely.geometry import box

from rmstrokes import strokefont
from rmstrokes.shapes import FILL_STYLES, SHAPES, region_strokes, shape_region
from rmstrokes.vectorize import STYLES, coverage, ink, load_art, svg_strokes_local
from strokes_helpers import bounds


@pytest.mark.parametrize("style", STYLES)
def test_svg_strokes_stay_in_the_box(icon, style):
    strokes = svg_strokes_local(str(icon), 200.0, None, style)
    x0, y0, x1, y1 = bounds(strokes)
    assert x0 >= -2 and y0 >= -2 and x1 <= 202 and y1 <= 202
    if style == "white-fill":
        assert si.PenColor.WHITE in {s.color for s in strokes}


def test_filled_svg_covers_the_dark_parts_and_keeps_the_hole(icon):
    art = load_art(icon, 200.0)
    strokes = svg_strokes_local(str(icon), 200.0, None, "filled")
    covered, _ = coverage(strokes, art.dark)
    assert covered > 0.97
    hole = art.light.intersection(box(0, 0, 100, 200))  # the light hole in the disc
    assert ink(strokes).intersection(hole).area / hole.area < 0.1


def test_unknown_style(icon):
    with pytest.raises(ValueError, match="unknown style"):
        svg_strokes_local(str(icon), 100.0, None, "sparkly")


@pytest.mark.parametrize("kind", SHAPES)
@pytest.mark.parametrize("style", FILL_STYLES)
def test_every_shape_in_every_style(kind, style):
    region = shape_region(kind, 120)
    strokes = region_strokes(region, style, 3.0)
    assert strokes
    assert ink(strokes).difference(region.buffer(0.5)).area < 0.01 * region.area
    if style in ("filled", "grey"):
        assert coverage(strokes, region)[0] > 0.95


def test_shape_aspects_and_errors():
    assert shape_region("tag", 100).bounds[3] == pytest.approx(62)
    assert shape_region("circle", 100, 50).bounds[3] == pytest.approx(50)
    with pytest.raises(ValueError, match="unknown shape"):
        shape_region("blob", 10)
    with pytest.raises(ValueError, match="fill style"):
        region_strokes(shape_region("circle", 10), "sparkly", 1)


def test_stroke_font_covers_letters_and_digits():
    text = "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-+.,!?':/#()"
    assert not strokefont.missing_glyphs(text + text.lower())
    for ch in text:
        x0, y0, x1, y1 = bounds(strokefont.glyph_strokes(ch, 0, 0, 60, 2))
        assert -1 <= x0 and x1 <= 43 and -3 <= y0 and y1 <= 69, ch  # a 40 x 60 cell (tails allowed)


def test_text_is_centred_and_errors_are_clear():
    strokes = strokefont.text_strokes("AB 12", 500, 300, 60, 2)
    x0, y0, x1, y1 = bounds(strokes)
    assert (x0 + x1) / 2 == pytest.approx(500, abs=2) and (y0 + y1) / 2 == pytest.approx(300, abs=2)
    assert x1 - x0 == pytest.approx(strokefont.text_width("AB 12", 60), abs=1)
    with pytest.raises(ValueError, match="stroke font has no"):
        strokefont.text_strokes("café", 0, 0, 10, 1)
