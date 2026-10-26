"""The intro page: six basics cards, a practice token, and each template's own part, on one page."""
import pytest

from rmstrokes.design import FALLBACK, get_style
from rmstrokes.devices import DEVICES
from rmstrokes.geometry import Rect, page_size
from rmstrokes.intro import PRACTICE_LAYER, IntroSpec, _layout, basics, intro_page, intro_style, token_maker
from rmstrokes.layers import Document, Layer, Page
from rmstrokes.tokens import Token
from rmstrokes.vectorize import Stroke
from strokes_helpers import pdf_text

SPEC = IntroSpec("Using the sheet", ("Tick a box.", "Move a tag."), layer="Marks", thing="mark",
                 handwriting="Notes")
CARDS = ("Pick the layer", "Lasso it", "Drag it", "Name it", "Show or hide", "Try it")


def _example(landscape):
    return Page(lambda p: p.rect(Rect(50, 50, 400, 300), stroke="#000000", width=3),
                [Layer("Marks", [Stroke(((100.0, 100.0), (300.0, 100.0)), 4.0)])], landscape=landscape)


def _overlap(a: Rect, b: Rect) -> bool:
    return a.x < b.right - 1e-6 and b.x < a.right - 1e-6 and a.y < b.bottom - 1e-6 and b.y < a.bottom - 1e-6


@pytest.mark.parametrize("landscape", [False, True])
@pytest.mark.parametrize("device", list(DEVICES))
def test_fits_every_device_and_orientation(device, landscape):
    dev = DEVICES[device]
    page = intro_page(dev, [(SPEC, _example(landscape))], landscape=landscape, title="Practice sheet")
    assert page.kind == "intro" and page.landscape == landscape
    practice = page.layer(PRACTICE_LAYER).strokes
    assert practice
    w, h = page_size(dev, landscape)
    assert all(0 <= x <= w and 0 <= y <= h for s in practice for x, y in s.points)
    text = pdf_text(Document(dev, [page]).render_pdf())
    for words in ("Practice sheet", *CARDS, "Using the sheet", "Tick a box.", "Marks"):
        assert words in text, words


@pytest.mark.parametrize("landscape", [False, True])
@pytest.mark.parametrize("device", list(DEVICES))
def test_nothing_overlaps_and_everything_is_inside_the_margins(device, landscape):
    dev = DEVICES[device]
    two = [(SPEC, _example(landscape)), (IntroSpec("Second part", ("Do this.", "Then that.")), None)]
    for parts in ([(SPEC, _example(landscape))], two):
        lay = _layout(dev, landscape, parts, "Practice sheet", intro_style(None, dev))
        W, H = page_size(dev, landscape)
        boxes = [r for _, r in lay.boxes]
        for r in boxes:
            assert lay.margin - 1 <= r.x and r.right <= W - lay.margin + 1, r
            assert lay.margin - 1 <= r.y and r.bottom <= lay.footer_y, r
        for i, a in enumerate(boxes):
            for b in boxes[i + 1:]:
                assert not _overlap(a, b), (a, b)
        # the practice token sits inside the Try it card's scene
        scene = next(sc for step, sc, _ in lay.cards if step.title == "Try it")
        page = intro_page(dev, parts, landscape=landscape, title="Practice sheet")
        xs = [x for s in page.layer(PRACTICE_LAYER).strokes for x, _ in s.points]
        ys = [y for s in page.layer(PRACTICE_LAYER).strokes for _, y in s.points]
        assert scene.x <= min(xs) and max(xs) <= scene.right and scene.y <= min(ys) and max(ys) <= scene.bottom


def test_two_templates_share_one_page():
    other = IntroSpec("Second part", ("Do this.",), layer="Pins")
    page = intro_page(DEVICES["rm2"], [(SPEC, None), (other, None)])
    text = pdf_text(Document(DEVICES["rm2"], [page]).render_pdf())
    assert "Using the sheet" in text and "Second part" in text and "Pins" in text


def test_the_cards_are_one_short_sentence_each():
    for parts in ([SPEC], [IntroSpec("x")], [IntroSpec("x", name_tags=False, handwriting="Notes")]):
        steps = basics(parts)
        assert len(steps) == 6
        for s in steps:
            assert s.text.count(".") == 1 and s.text.endswith(".") and len(s.text) <= 48, s.text


def test_without_name_tags_the_write_card_is_about_notes():
    titles = [s.title for s in basics([IntroSpec("x", layer="Words", handwriting="Notes", name_tags=False)])]
    assert "Take notes" in titles and "Name it" not in titles


PIN = token_maker(Token("pin", size_mm=6, style="filled"))


def test_the_practice_token_is_the_templates_own():
    """A template's own token (IntroSpec.token) is the one the cards draw and you practise on."""
    rm2 = DEVICES["rm2"]
    own = IntroSpec("Map", ("Drag a pin in.",), layer="Pins", thing="pin", name_tags=False, token=PIN)
    generic = IntroSpec("Map", ("Drag a pin in.",), layer="Pins", thing="pin", name_tags=False)
    strokes = [intro_page(rm2, [(spec, None)]).layer(PRACTICE_LAYER).strokes for spec in (own, generic)]
    assert strokes[0] and strokes[0] != strokes[1]
    assert basics([own])[-1].text == "Move this pin onto its outline."
    assert basics([generic])[-1].text == "Move this token onto its outline."


def test_a_mixed_document_keeps_a_demo_token_with_a_name_tag():
    """Pins have no tag: next to a template with name tags, the tagged generic token stands in."""
    pins = IntroSpec("Map", ("Drag a pin in.",), layer="Pins", thing="pin", name_tags=False, token=PIN)
    lay = _layout(DEVICES["rm2"], False, [(pins, None), (SPEC, None)], "Mixed", intro_style(None, DEVICES["rm2"]))
    assert lay.kit.maker is None and lay.kit.token(100).tag is not None
    assert basics([pins, SPEC])[-1].text == "Move this token onto its outline."


def test_the_intro_speaks_in_the_system_style():
    rm2, pro = DEVICES["rm2"], DEVICES["pro"]
    assert intro_style(None, pro).color_ok
    assert intro_style(get_style("default", pro), pro).name == "color"
    assert intro_style(get_style("color", rm2), rm2).name == "default"    # no colour where none shows
    page = intro_page(rm2, [(SPEC, None)], style=get_style("default", rm2))
    assert "AtkinsonHyperlegibleNext-Regular" in page.fonts
    assert set(page.fonts) <= set(get_style("default", rm2).fonts) | set(FALLBACK.values())


def test_too_much_text_is_refused():
    wordy = IntroSpec("Long", tuple("A very long step that goes on and on. " * 8 for _ in range(30)))
    with pytest.raises(ValueError, match="doesn't fit"):
        intro_page(DEVICES["move"], [(wordy, None)])
