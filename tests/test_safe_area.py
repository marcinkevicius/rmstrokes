"""Safe area: every page of the built-in template and the examples, intro page included, keeps its print
and its strokes inside `Style.safe_area()` on every device: inside the margin, and clear of the strip
at the left edge that the open toolbar covers."""
from pathlib import Path

import pytest

from rmstrokes.design import get_style
from rmstrokes.devices import DEVICES, get_device
from rmstrokes.recipe import Section, build_document, build_recipe, load_recipe
from rmstrokes.templates import get_template

pdfium = pytest.importorskip("pypdfium2")
np = pytest.importorskip("numpy")

ROOT = Path(__file__).resolve().parents[1]
TEMPLATES = ["gaps", str(ROOT / "examples/templates/sorting.toml"),
             str(ROOT / "examples/character_mix/character_mix.py")]
SLACK_MM = 0.5  # anti-aliasing and the odd descender


def outside(doc) -> list[str]:
    """Each page whose ink (background and printed strokes) leaves the safe area, and by how much."""
    dev = doc.device
    style = get_style("default", dev)
    slack = dev.mm(SLACK_MM)
    pdf = pdfium.PdfDocument(doc.render_pdf(print_strokes=True))
    bad = []
    for n, (page, built) in enumerate(zip(pdf, doc.pages), 1):
        safe = style.safe_area(built.landscape)
        img = np.asarray(page.render(scale=dev.dpi / 72).to_pil().convert("L"))
        ys, xs = np.nonzero(img < 250)
        if not len(xs):
            continue
        over = {"left": safe.x - xs.min(), "top": safe.y - ys.min(),
                "right": xs.max() + 1 - safe.right, "bottom": ys.max() + 1 - safe.bottom}
        over = {side: v / dev.mm(1) for side, v in over.items() if v > slack}
        if over:
            sides = ", ".join(f"{side} {v:.1f} mm" for side, v in over.items())
            bad.append(f"{dev.key} page {n} ({built.kind or 'page'}): over the {sides}")
    return bad


@pytest.mark.parametrize("device", list(DEVICES))
@pytest.mark.parametrize("name", TEMPLATES, ids=lambda t: Path(t).stem)
def test_template_pages_stay_in_the_safe_area(name, device):
    template = get_template(name)
    theme = "color" if get_device(device).color and "color" in template.themes() else "default"
    values = template.validate({"device": device, "theme": theme})
    doc = build_document([Section(template, values)], device, intro=True)
    assert not outside(doc)


@pytest.mark.parametrize("device", list(DEVICES))
def test_recipe_pages_stay_in_the_safe_area(device):
    doc = build_recipe(load_recipe(ROOT / "examples/reading.toml", device=device))
    assert not outside(doc)


def test_safe_area_clears_the_toolbar_and_the_margin():
    for key in DEVICES:
        style = get_style("default", key)
        for landscape in (False, True):
            r = style.safe_area(landscape)
            assert r.x == pytest.approx(style.mm(style.spacing.toolbar))
            assert r.y == pytest.approx(style.margin())
            assert r.x + r.w + style.margin() == pytest.approx(get_device(key).height if landscape
                                                                else get_device(key).width)
