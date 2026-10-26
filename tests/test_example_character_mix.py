"""The character mix & match example: Open Peeps parts as movable tokens, one layer per kind."""
import hashlib
import re
from pathlib import Path

import pytest
from shapely.geometry import LineString, MultiPoint, box

from rmstrokes import token_art
from rmstrokes.devices import DEVICES, get_device
from rmstrokes.layers import Document
from rmstrokes.params import SchemaError
from rmstrokes.templates import get_template
from strokes_helpers import layers, pdf_text

ROOT = Path(__file__).resolve().parents[1]
EXAMPLE = ROOT / "examples" / "character_mix"
PARTS = sorted((EXAMPLE / "parts").glob("*.svg"))
LAYERS = ["Bodies", "Heads", "Faces", "Facial hair", "Accessories"]


@pytest.fixture(scope="module")
def template():
    return get_template(str(EXAMPLE / "character_mix.py"))


def build(template, values=None, device="rm2", theme="default"):
    v = template.validate({**(values or {}), "device": device, "theme": theme})
    return template.pages(v, template.context(get_device(device), v["theme"])), v


@pytest.mark.parametrize("device", list(DEVICES))
def test_builds_on_every_device(template, device):
    theme = "color" if get_device(device).color else "default"
    (page,), _ = build(template, device=device, theme=theme)
    assert [layer.name for layer in page.layers] == LAYERS and page.handwriting == "Handwriting"
    assert all(layer.strokes for layer in page.layers)
    text = pdf_text(Document(get_device(device), [page]).render_pdf())
    assert "Mix & match" in text and "Who is this?" in text and "Open Peeps by Pablo Stanley" in text


def test_a_layer_per_kind_with_every_part_once(template, tmp_path):
    (page,), _ = build(template)
    placed = page.meta["layout"].placed
    assert [len(placed[k]) for k in placed] == [4, 6, 6, 3, 3]
    assert sorted(part.path for boxes in placed.values() for part, _ in boxes) == PARTS
    out = tmp_path / "mix.rmdoc"
    Document(get_device("rm2"), [page]).write_rmdoc(out)
    names = [name for name, _ in layers(out)[0]]
    assert names[:len(LAYERS)] == LAYERS and "Handwriting" in names


def test_a_lasso_round_one_part_takes_only_that_part(template):
    """Every part is one compact cluster: the loop round its box catches its strokes and nothing else
    on its layer."""
    (page,), _ = build(template)
    lay = page.meta["layout"]
    device = get_device("rm2")
    assert list(lay.placed) == ["bodies", "heads", "faces", "facial-hair", "accessories"]
    for layer, boxes in zip(page.layers, lay.placed.values()):
        start = 0
        for part, rect in boxes:
            n = len(token_art(part.token(lay.k), device).strokes)
            cluster = layer.strokes[start:start + n]
            start += n
            loop = rect.inset(-device.mm(1.2))
            region = box(loop.x, loop.y, loop.right, loop.bottom)
            inside = [s for s in layer.strokes
                      if region.contains(LineString(s.points) if len(s.points) > 1 else MultiPoint(s.points))]
            assert inside == cluster, part.path.name
        assert start == len(layer.strokes)


def test_cards_and_parts_are_checked(template):
    with pytest.raises(SchemaError):
        template.validate({"cards": 5})
    with pytest.raises(SchemaError, match="unknown part kind"):
        template.validate({"parts": ["hats"]})
    (page,), _ = build(template, {"cards": 1, "parts": ["faces", "heads"]})
    assert [layer.name for layer in page.layers] == ["Heads", "Faces"], "bottom to top, whatever the order given"
    assert len(page.meta["layout"].cards) == 1


def test_every_part_is_listed_with_its_hash():
    attribution = (ROOT / "ATTRIBUTION.md").read_text()
    assert len(PARTS) == 22
    for path in PARTS:
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        assert re.search(rf"^\| `{re.escape(path.name)}` \|.*`{digest}` \|$", attribution, re.M), path.name


def test_parts_are_plain():
    """Cut clean: ASCII only, no editor metadata or ids, the licence named in each file."""
    for path in PARTS:
        text = path.read_text()
        assert text.isascii(), path.name
        assert not re.search(r"sketch|<desc|<title|\bid=", text, re.I), path.name
        assert "CC0" in text and "openpeeps.com" in text
