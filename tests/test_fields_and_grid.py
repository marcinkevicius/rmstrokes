"""The grid trays are laid out on, and write-in fields on the background."""
import pytest

from rmstrokes.devices import DEVICES
from rmstrokes.fields import WriteIn, draw_write_in
from rmstrokes.geometry import FitError, Rect, grid_cells
from rmstrokes.layers import Document, Page
from strokes_helpers import pdf_text

RM2 = DEVICES["rm2"]


def test_grid_rows_are_centred_and_inside():
    area = Rect(100, 100, 1000, 400)
    cells = grid_cells(area, 7, 180, 150, gap=10)
    assert len(cells) == 7
    rows = sorted({c.y for c in cells})
    assert len(rows) == 2
    for c in cells:
        assert area.x <= c.x and c.right <= area.right + 1e-6
        assert area.y <= c.y and c.bottom <= area.bottom + 1e-6
    last = [c for c in cells if c.y == rows[1]]
    assert (last[0].x + last[-1].right) / 2 == pytest.approx(area.center[0])
    assert len({c.y for c in grid_cells(area, 6, 100, 100, columns=2)}) == 3


def test_grid_errors_say_what_doesnt_fit():
    with pytest.raises(FitError, match="don't fit"):
        grid_cells(Rect(0, 0, 300, 100), 10, 100, 100)
    with pytest.raises(FitError, match="at least one"):
        grid_cells(Rect(0, 0, 300, 100), 0, 10, 10)


def test_write_in_fields():
    fields = [(WriteIn("Today I will", after="first"), Rect(100, 100, 1200, 80)),
              (WriteIn("Name", kind="box", value="Ana"), Rect(100, 300, 600, 200)),
              (WriteIn("Notes", kind="lines"), Rect(100, 600, 1200, 400))]

    def draw(p):
        for f, r in fields:
            draw_write_in(p, f, r)
    text = pdf_text(Document(RM2, [Page(draw, handwriting="W")]).render_pdf())
    for word in ("Today I will", "first", "Name", "Ana", "Notes"):
        assert word in text
    with pytest.raises(ValueError, match="kind"):
        WriteIn("x", kind="circle")
