"""rmstrokes explain: the five steps from a template's real page, the CLI, the gallery section and
the committed docs page (its text must match what the command writes)."""
import re
from pathlib import Path

import pytest

from rmstrokes import cli, gallery
from rmstrokes.explain import STEPS, explain, html_text, markdown, placements
from rmstrokes.templates import get_template

ROOT = Path(__file__).resolve().parents[1]
CHARACTER_MIX = "examples/character_mix/character_mix.py"
DOC = ROOT / "docs" / "how-a-page-is-built.md"
DOC_IMAGES = "how-a-page-is-built"
DOC_COMMAND = (f"rmstrokes explain gaps {CHARACTER_MIX} -o docs/{DOC_IMAGES} "
               f"--markdown docs/{DOC_IMAGES}.md")


def test_gaps_pages_list_their_areas_and_placements():
    t = get_template("gaps")
    ex = explain(t, "rm2", render=False)
    page = ex.page
    kinds = [label for label, _ in page.meta["areas"]]
    assert kinds.count("text") == 2 and "passage" in kinds and "tray bank" in kinds
    pls = placements(page)
    assert [pl.token.label for pl in pls] == ["clouds", "rain", "sun", "vapour"]
    assert {pl.layer for pl in pls} == {"Words"}
    # The placements are the page's strokes, token by token.
    assert [s for pl in pls for s in pl.strokes()] == page.layer("Words").strokes


def test_the_steps_text_follows_the_page():
    ex = explain("gaps", "rm2", {"words": ["sun", "rain", "wind"]}, render=False)
    assert [(s.key, s.title) for s in ex.steps] == list(STEPS)
    text = {s.key: s.text for s in ex.steps}
    assert "`gaps` is built in" in text["inputs"] and "`rounded` shape" in text["inputs"]
    assert "1404 × 1872 px" in text["layout"] and "3 tokens" in text["layout"]
    assert "“sun”" in text["strokes"]
    assert "“Words”" in text["layers"] and "“Notes” (empty)" in text["layers"]
    assert "unverified" not in text["finished"]
    assert "unverified" in explain("gaps", "pro", render=False).steps[-1].text


def test_an_svg_template_explains_its_svg():
    ex = explain(str(ROOT / CHARACTER_MIX), "rm2", {"parts": ["heads"], "cards": 1}, render=False)
    text = {s.key: s.text for s in ex.steps}
    assert "SVG files read as vector art" in text["inputs"]
    assert re.search(r"the SVG `head-[a-z-]+\.svg` is read into dark and light regions", text["strokes"])


def test_pictures(tmp_path):
    pytest.importorskip("pypdfium2")
    ex = explain("gaps", "pro")
    for step in ex.steps:
        w, h = step.image.size
        assert 800 < w < 2600 and 400 < h < 1000, (step.key, step.image.size)
    # The layers step has a panel per layer, plus the background: wider than the inputs step.
    assert ex.steps[3].image.size[0] > ex.steps[0].image.size[0]


def test_a_template_without_layout_data_still_explains():
    pytest.importorskip("pypdfium2")
    from rmstrokes import Layer, Page, Stroke, Template

    class Bare(Template):
        name = "bare"

        def pages(self, values, ctx):
            return [Page(draw=lambda p: None, layers=[Layer("Ink", [Stroke(((10, 10), (200, 300)), 4)])])]

    ex = explain(Bare(), "rm2")
    assert all(s.image is not None for s in ex.steps)
    assert "1 stroke on this page" in ex.steps[2].text


def test_cli_writes_the_steps_documents_and_markdown(tmp_path, capsys):
    pytest.importorskip("pypdfium2")
    out, md = tmp_path / "pics", tmp_path / "doc" / "explain.md"
    assert cli.main(["explain", "--device", "move", "-o", str(out), "--markdown", str(md)]) == 0
    names = sorted(p.name for p in out.iterdir())
    assert names == sorted([f"gaps-move-{n}-{key}.png" for n, (key, _) in enumerate(STEPS, 1)]
                           + ["gaps-move.pdf", "gaps-move.rmdoc"])
    text = md.read_text()
    assert "](../pics/gaps-move-3-strokes.png)" in text and "**Unverified:**" in text
    assert "unverified" in capsys.readouterr().out


def test_the_committed_doc_is_current():
    """docs/how-a-page-is-built.md is the command's output: regenerate it (the command is in its
    header) after changing the steps' text, and its pictures are committed next to it."""
    explainers = [explain("gaps", "rm2", render=False), explain(str(ROOT / CHARACTER_MIX), "rm2", render=False)]
    assert DOC.read_text(encoding="utf-8") == markdown(explainers, DOC_IMAGES, DOC_COMMAND), \
        f"regenerate it: from the repository root, run `{DOC_COMMAND} --no-documents`"
    linked = re.findall(r"\]\((how-a-page-is-built/[^)]+\.png)\)", DOC.read_text())
    assert len(linked) == 10
    assert all((DOC.parent / p).is_file() for p in linked)
    assert sorted(p.name for p in (DOC.parent / DOC_IMAGES).iterdir()) == sorted(Path(p).name for p in linked)


def test_gallery_section(tmp_path):
    pytest.importorskip("pypdfium2")
    config = tmp_path / "gallery.toml"
    config.write_text('devices = ["rm2"]\nexplain = ["gaps", "nope"]\n')
    with pytest.raises(Exception, match="explain: unknown template 'nope'"):
        gallery.load_gallery(config)
    config.write_text('devices = ["rm2", "pro"]\nexplain = ["gaps"]\n')
    g = gallery.load_gallery(config, only=["explain"])
    assert g.jobs == [] and g.explain == ["gaps"]
    assert any(line.startswith("explain ") and "[unverified device]" in line for line in gallery.describe(g))
    out = tmp_path / "out"
    gallery.run_gallery(g, out, log=lambda line: None)
    assert [x.error for x in g.explained] == [None, None]
    index = (out / "index.html").read_text()
    assert "<section id='explain'>" in index and "href=#explain" in index
    for n, (key, _) in enumerate(STEPS, 1):
        assert f"explain/pro/gaps-pro-{n}-{key}.png" in index
        assert (out / "explain" / "rm2" / f"gaps-rm2-{n}-{key}.png").is_file()
    assert "unverified on a real tablet" in index
    # without explain in --only, the section is left out
    assert gallery.load_gallery(config, only=["templates"]).explain == []


def test_html_text():
    assert html_text("a `<b>` and “x”") == "a <code>&lt;b&gt;</code> and “x”"
