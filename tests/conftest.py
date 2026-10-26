import pytest

from strokes_helpers import ICON_SVG


@pytest.fixture
def icon(tmp_path):
    p = tmp_path / "icon.svg"
    p.write_text(ICON_SVG)
    return p
