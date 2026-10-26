"""Design tokens (design.py): the e-ink rules hold for every theme and device, themes are chosen per
template, and the specimen builds."""
import io
import itertools
import zipfile

import pytest
from pypdf import PdfReader
from rmscene import scene_items as si

from rmstrokes import fonts
from rmstrokes.cli import main
from rmstrokes.datatemplate import DataTemplate
from rmstrokes.design import (
    DISPLAY,
    FALLBACK,
    GREYS,
    MIN_CONTRAST,
    PRO_ACCENTS,
    ROLES,
    THEMES,
    contrast,
    delta_e,
    get_style,
    grey_uses,
    lab,
)
from rmstrokes.devices import DEVICES
from rmstrokes.layers import Document
from rmstrokes.specimen import specimen_document
from rmstrokes.templates import Context, Template, get_template
from rmstrokes.tokens import NameTag, Token, token_art
from strokes_helpers import pdf_text

STYLES = [(t, d) for t in THEMES for d in DEVICES]


@pytest.mark.parametrize("theme, device", STYLES)
def test_every_role_has_an_existing_font_and_a_readable_size(theme, device):
    style = get_style(theme, device)
    for role in ROLES:
        t = style.type(role)
        fonts.font(t.font)  # bundled, loads
        assert t.size_mm >= 2.5, f"{role}: {t.size_mm} mm is under the 7 pt floor"
        assert not fonts.missing_glyphs("Aa0123456789 Il1 O0 ,.:;!?()-", t.font)


@pytest.mark.parametrize("device", DEVICES)
def test_the_system_retires_the_monospace_except_for_numbers(device):
    style = get_style("default", device)
    mono = {r for r in ROLES if "Mono" in style.font(r)}
    assert mono <= {"numeric"}  # numbers only, and only where a font package provides the monospace
    assert set(style.fonts) <= BUNDLED | set(FALLBACK)  # the system's faces only, no other theme's


BUNDLED = {"AtkinsonHyperlegibleNext-Regular", "AtkinsonHyperlegibleNext-Italic", "AtkinsonHyperlegibleNext-SemiBold"}


def test_bundles_three_atkinson_faces_with_their_licence():
    files = {p.name for p in fonts.BUNDLED_FONTS.iterdir() if not p.name.startswith(".")}
    assert files == {f"{n}.ttf" for n in BUNDLED} | {"OFL-AtkinsonHyperlegibleNext.txt"}
    assert "SIL OPEN FONT LICENSE Version 1.1" in (fonts.BUNDLED_FONTS / "OFL-AtkinsonHyperlegibleNext.txt").read_text()


@pytest.fixture
def bundled_fonts_only(monkeypatch):
    """No font packages and no registered sources: the engine on its own."""
    monkeypatch.setattr(fonts, "_installed_sources", lambda: ())
    monkeypatch.setattr(fonts, "_sources", [])
    fonts.font.cache_clear()
    yield
    fonts.font.cache_clear()


@pytest.mark.parametrize("theme, device", [(t, d) for t in ("default", "color") for d in DEVICES])
def test_without_font_packages_every_role_falls_back_to_a_bundled_face(bundled_fonts_only, theme, device):
    style = get_style(theme, device)
    assert set(style.fonts) <= BUNDLED
    assert style.font("title") == style.font("small") == "AtkinsonHyperlegibleNext-SemiBold"
    assert style.font("numeric") == "AtkinsonHyperlegibleNext-Regular"
    with pytest.raises(ValueError, match="not found"):
        fonts.font_path(DISPLAY)


def test_without_font_packages_a_template_embeds_only_the_bundled_faces(bundled_fonts_only):
    t = get_template("gaps")
    v = t.validate({"theme": "default", "title": "Gaps 0123"})
    page = t.pages(v, t.context(DEVICES["rm2"], "default"))[0]
    pdf = Document(DEVICES["rm2"], [page]).render_pdf()
    used = {str(f.get("/BaseFont")).split("+")[-1] for p in PdfReader(io.BytesIO(pdf)).pages
            for f in p["/Resources"]["/Font"].values()}
    assert used and used <= BUNDLED, used


def test_scale_is_ordered_and_the_move_shrinks_only_big_type():
    rm2, move = get_style("default", "rm2"), get_style("default", "move")
    sizes = [rm2.type(r).size_mm for r in ("title", "heading", "label", "field", "small")]
    assert sizes == sorted(sizes, reverse=True)
    assert move.type("title").size_mm < rm2.type("title").size_mm
    assert move.type("small").size_mm == rm2.type("small").size_mm
    assert move.type("label").size_mm == rm2.type("label").size_mm


def test_greys_are_panel_levels():
    for name, hexv in GREYS.items():
        level = int(hexv[1:3], 16)
        assert hexv[1:3] == hexv[3:5] == hexv[5:7] and level % 0x11 == 0, name


@pytest.mark.parametrize("theme", ["default", "color"])
def test_semantic_greys_keep_their_contrast_floors(theme):
    s = get_style(theme, "rm2")
    for tok in ("ink", "ink-2", "muted"):
        assert contrast(s.color(tok)) >= MIN_CONTRAST["text"], tok
    assert contrast(s.color("rule")) >= MIN_CONTRAST["line"]
    assert contrast(s.color("guide")) >= MIN_CONTRAST["guide"]
    for tok in ("surface-strong", "surface", "surface-faint"):
        assert "fill" in grey_uses(s.color(tok))
        assert contrast("#000000", s.color(tok)) >= MIN_CONTRAST["text"]
    # text roles never use a grey too light for text
    for role in ROLES:
        assert contrast(s.color(s.type(role).color)) >= MIN_CONTRAST["text"], role


def test_pro_palette_is_soft_and_distinguishable():
    inks = [ink for _, ink, _ in PRO_ACCENTS]
    tints = [tint for _, _, tint in PRO_ACCENTS]
    for ink in inks:
        L, a, b = lab(ink)
        assert 35 <= L <= 52 and (a * a + b * b) ** 0.5 <= 60
        assert contrast(ink) >= MIN_CONTRAST["line"]
    for tint in tints:
        assert 82 <= lab(tint)[0] <= 92
        assert contrast("#000000", tint) >= MIN_CONTRAST["text"]
    assert min(delta_e(a, b) for a, b in itertools.combinations(inks, 2)) >= 20
    assert min(delta_e(a, b) for a, b in itertools.combinations(tints, 2)) >= 13


def test_color_theme_has_pair_and_accent_tokens_and_pens():
    c, g = get_style("color", "pro"), get_style("default", "pro")
    assert c.color("pair-a") == PRO_ACCENTS[0][1] and c.color("pair-b") == PRO_ACCENTS[1][1]
    assert c.pen("pair-a") == si.PenColor.BLUE and c.pen("pair-b") == si.PenColor.RED
    assert g.pen("pair-a") == si.PenColor.BLACK
    for i in range(1, len(PRO_ACCENTS) + 1):
        assert g.color(f"accent-{i}") in GREYS.values()
    assert c.color("#123456") == "#123456"
    with pytest.raises(ValueError, match="unknown colour token 'tomato'"):
        c.color("tomato")


def test_unknown_theme_is_refused():
    with pytest.raises(ValueError, match="unknown design theme 'neon'"):
        get_style("neon", "rm2")


# --------------------------------------------------------------------------- per template


def test_templates_offer_the_design_themes_and_map_their_own():
    class Mine(Template):
        name = "mine"

    class Mapped(Template):
        name = "mapped"
        theme_styles = {"default": "color"}

    class Tinted(Template):
        name = "tinted"
        fallback_style = "color"

    dev = DEVICES["rm2"]
    assert Mine().themes() == list(THEMES)
    assert Mine().style_for("color", dev).name == "color"
    assert Mapped().style_for("default", dev).name == "color"
    assert Mine().style_for("custom", dev).name == "default"  # a template's own theme: the fallback
    assert Tinted().style_for("custom", dev).name == "color"
    assert Context(dev, "default").style.name == "default"
    assert Context(dev, "custom").style.name == "default"


def test_another_package_can_register_a_theme():
    from rmstrokes import design
    from rmstrokes.design import Lines, Style, make_palette, register_theme
    with pytest.raises(ValueError, match="built-in"):
        register_theme("default", lambda d: None)
    base = get_style("default", "rm2")
    register_theme("test-ink", lambda d: Style("test-ink", d, False, dict(base.text),
                                               make_palette({**base.palette, "rule": "#000000"}, False), Lines()))
    try:
        assert "test-ink" in THEMES and get_style("test-ink", "rm2").color("rule") == "#000000"
    finally:
        THEMES.remove("test-ink")
        design._registered.pop("test-ink")
        design._style.cache_clear()


@pytest.mark.parametrize("theme, expect", [("default", "AtkinsonHyperlegibleNext")])
def test_builtin_template_fonts_follow_the_theme(theme, expect):
    t = get_template("gaps")
    v = t.validate({"theme": theme})
    page = t.pages(v, t.context(DEVICES["rm2"], theme))[0]
    pdf = Document(DEVICES["rm2"], [page]).render_pdf()
    used = {str(f.get("/BaseFont")) for p in PdfReader(io.BytesIO(pdf)).pages
            for f in p["/Resources"]["/Font"].values()}
    assert any(expect in u for u in used), used


def test_data_template_roles_and_colour_tokens():
    t = DataTemplate({"name": "x", "handwriting": "W", "background": [
        {"type": "text", "text": "Group", "font": "caps", "x": 10, "y": 20, "color": "accent-2"},
        {"type": "rect", "x": 10, "y": 30, "w": 20, "h": 10, "fill": "surface", "stroke": False},
    ]})
    page = t.pages(t.validate({"theme": "color", "device": "pro"}), t.context(DEVICES["pro"], "color"))[0]
    assert "GROUP" in pdf_text(Document(DEVICES["pro"], [page]).render_pdf())
    bad = DataTemplate({"name": "x", "handwriting": "W",
                        "background": [{"type": "line", "x1": 0, "y1": 0, "x2": 1, "y2": 1, "color": "tomato"}]})
    with pytest.raises(Exception, match="color: unknown colour token 'tomato'"):
        bad.pages(bad.validate({}), Context(DEVICES["rm2"], "default"))


# --------------------------------------------------------------------------- knock-out and specimen


def test_knockout_tag_is_white_ink_inside_the_tag():
    dev = DEVICES["rm2"]
    plain = token_art(Token("circle", 9, name_tag=NameTag(24, 7.5)), dev)
    ko = token_art(Token("circle", 9, name_tag=NameTag(24, 7.5, knockout=True)), dev)
    white = [s for s in ko.strokes if s.color == si.PenColor.WHITE]
    assert white and not any(s.color == si.PenColor.WHITE for s in plain.strokes)
    tag = ko.tag
    assert all(tag.x <= x <= tag.right and tag.y <= y <= tag.bottom for s in white for x, y in s.points)
    assert ko.width == plain.width and ko.height == plain.height


@pytest.mark.parametrize("theme, device", [("default", "rm2"), ("color", "pro"), ("default", "move")])
def test_specimen_builds(theme, device):
    doc = specimen_document(device, theme)
    assert doc.pages and all(p.kind == "specimen" for p in doc.pages)
    assert any(p.strokes for p in doc.pages)  # the movable tokens
    text = "".join(pdf_text(doc.render_pdf(), i) for i in range(len(doc.pages)))
    assert "Design system" in text and "Paper Pro colour" in text
    assert ("unverified" in text) == (not DEVICES[device].verified)


def test_specimen_command_writes_rmdoc_pdf_and_png(tmp_path, capsys):
    assert main(["specimen", "-o", str(tmp_path)]) == 0
    names = {p.name for p in tmp_path.iterdir()}
    for stem in ("specimen-rm2-default", "specimen-pro-color"):
        assert f"{stem}.rmdoc" in names and f"{stem}.pdf" in names
        assert any(n.startswith(stem) and n.endswith(".png") for n in names)
    assert zipfile.is_zipfile(tmp_path / "specimen-rm2-default.rmdoc")
    assert "Paper Pro: unverified" in capsys.readouterr().out
