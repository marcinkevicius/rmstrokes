"""Tokens: one compact, contiguous cluster per object; the name tag on the same layer, touching."""
import dataclasses

import pytest
from rmscene import scene_items as si
from shapely.geometry import LineString, MultiPoint

from rmstrokes.devices import DEVICES
from rmstrokes.geometry import Rect, grid_cells
from rmstrokes.tokens import NameTag, Token, token_art
from rmstrokes.vectorize import ink
from strokes_helpers import bounds

RM2 = DEVICES["rm2"]
TAGGED = Token("circle", size_mm=10, number=7, name_tag=NameTag(width_mm=20, height_mm=7))


def _split(art):
    """(shape and label strokes, tag strokes): the token without its tag is the first run."""
    n = len(token_art(dataclasses.replace(TAGGED, name_tag=None), RM2).strokes)
    return art.strokes[:n], art.strokes[n:]


def test_tag_touches_the_shape_and_everything_stays_in_the_footprint():
    art = token_art(TAGGED, RM2)
    shape, tag = _split(art)
    assert tag, "the tag is drawn"
    assert ink(shape).distance(ink(tag)) < RM2.mm(0.5)  # touching: one lasso takes both
    x0, y0, x1, y1 = bounds(art.strokes)
    pen = RM2.mm(TAGGED.pen_mm)
    assert x0 >= -pen and y0 >= -pen and x1 <= art.width + pen and y1 <= art.height + pen
    assert art.tag is not None and art.tag.y < art.shape.bottom  # overlaps the shape's edge
    assert art.tag.w == pytest.approx(RM2.mm(20)) and art.tag.h == pytest.approx(RM2.mm(7))


def test_the_tag_comes_last_so_the_cluster_is_one_run():
    art = token_art(TAGGED, RM2)
    _, tag = _split(art)
    for s in tag:  # every stroke after the shape's run belongs to the tag
        assert all(art.tag.x - 2 <= x <= art.tag.right + 2 and art.tag.y - 2 <= y <= art.tag.bottom + 2
                   for x, y in s.points)


def test_name_tag_to_the_right_and_line_style():
    right = token_art(Token("star", 12, name_tag=NameTag(18, 6, side="right", style="line")), RM2)
    assert right.tag.x < right.shape.right and right.width > right.shape.w + RM2.mm(15)
    with pytest.raises(ValueError, match="side"):
        NameTag(side="above")
    with pytest.raises(ValueError, match="style"):
        NameTag(style="cloud")


def test_label_colour_follows_the_fill():
    filled = token_art(Token("circle", 10, style="filled", label="A"), RM2)
    assert si.PenColor.WHITE in {s.color for s in filled.strokes}
    plain = token_art(Token("circle", 10, label="A"), RM2)
    assert {s.color for s in plain.strokes} == {si.PenColor.BLACK}


@pytest.mark.parametrize("shape", ["pin", "tag", "arrow", "star", "heart"])
def test_primitives_with_labels(shape):
    art = token_art(Token(shape, 14, label="9", style="white-fill"), RM2)
    assert len(art.strokes) > 3


def test_svg_token_with_icon(icon):
    art = token_art(Token(str(icon), 12, style="filled", name_tag=NameTag()), RM2)
    assert art.tag is not None and art.strokes
    with_icon = token_art(Token("circle", 12, icon=str(icon)), RM2)
    assert len(with_icon.strokes) > len(token_art(Token("circle", 12), RM2).strokes)


def test_token_errors(tmp_path):
    with pytest.raises(ValueError, match="neither one of"):
        token_art(Token("nothing.svg"), RM2)
    with pytest.raises(ValueError, match="token style"):
        token_art(Token("circle", style="glitter"), RM2)
    with pytest.raises(ValueError, match="stroke font has no"):
        token_art(Token("circle", label="é"), RM2)


def test_placed_and_rotated():
    art = token_art(TAGGED, RM2)
    up = art.placed(700, 900)
    x0, y0, x1, y1 = bounds(up)
    assert (x0 + x1) / 2 == pytest.approx(700, abs=RM2.mm(0.5))
    turned = art.placed(700, 900, 180)
    for a, b in zip(up, turned):
        for (ax, ay), (bx, by) in zip(a.points, b.points):
            assert (ax + bx, ay + by) == pytest.approx((1400, 1800))


def test_a_lasso_round_one_token_takes_only_that_token():
    """In a grid, the loop round one token's footprint (plus a hand's slack) catches all of its
    strokes and none of its neighbours'."""
    art = token_art(TAGGED, RM2)
    cells = grid_cells(Rect(100, 100, 1200, 600), 6, art.width + RM2.mm(2), art.height + RM2.mm(2))
    strokes = [s for cell in cells for s in art.placed(*cell.center)]
    per = len(art.strokes)
    clusters = [strokes[i * per:(i + 1) * per] for i in range(6)]
    for cell, cluster in zip(cells, clusters):
        loop = art.outline(*cell.center).buffer(RM2.mm(0.9))
        inside = [s for s in strokes if loop.contains(LineString(s.points) if len(s.points) > 1
                                                       else MultiPoint(s.points))]
        assert inside == cluster
