"""Recipes: one file, one document; mixed page types, copies, and the intro page on request."""
import json

import pytest

from rmstrokes.params import SchemaError
from rmstrokes.recipe import build_recipe, load_recipe, recipe_from_dict
from rmstrokes.rm import read_layers
from rmstrokes.rmdoc import read_rmdoc
from strokes_helpers import pdf_page_count, pdf_text

MIXED = '''
name = "Reading day"
device = "rm2"
intro = true

[[pages]]
template = "gaps"
title = "Our gaps"
words = ["one", "two"]

[[pages]]
template = "lines.toml"
copies = 3
'''

# A second template, next to the recipe: a ruled page with tokens.
RULED = '''
name = "lines"
title = "Ruled lines"

[intro]
title = "Using the lines"
steps = ["Drag a token onto a line."]

[[background]]
type = "lines"
x = 14
y = 30
w = "W - 28"
h = 100

[tokens.person]
shape = "circle"
size = 8
number = "n"

[[trays]]
name = "start"
token = "person"
count = 4
x = 14
y = "H - 40"
w = "W - 28"
h = 20

[[layers]]
name = "Tokens"
trays = ["start"]
'''


def test_a_recipe_with_mixed_pages_builds(tmp_path):
    (tmp_path / "day.toml").write_text(MIXED)
    (tmp_path / "lines.toml").write_text(RULED)
    doc = build_recipe(load_recipe(tmp_path / "day.toml"))
    assert [p.kind for p in doc.pages] == ["intro", "gaps", "lines", "lines", "lines"]
    result = doc.write(tmp_path / "day.rmdoc")
    rd = read_rmdoc(result.path)
    assert rd.metadata["visibleName"] == "Reading day" and pdf_page_count(rd.pdf) == 5
    names = [[n for n, _ in read_layers(rm)] for _, rm in rd.pages]
    assert names == [["Practice"], ["Notes", "Words"], ["Tokens"], ["Tokens"], ["Tokens"]]
    intro = pdf_text(rd.pdf, 0)
    assert "Reading day" in intro and "Filling the gaps" in intro and "Using the lines" in intro
    assert "Our gaps" in pdf_text(rd.pdf, 1)


def test_copies_gives_identical_pages(tmp_path):
    doc = build_recipe(recipe_from_dict({"pages": [{"template": "gaps", "copies": 4}]}))
    assert len(doc.pages) == 4
    result = doc.write(tmp_path / "c.rmdoc")
    lines = [read_layers(rm) for rm in result.rm]
    pts = [[[(p.x, p.y) for p in line.points] for _, ls in layer for line in ls] for layer in lines]
    assert all(p == pts[0] for p in pts) and pts[0]
    texts = {pdf_text(result.pdf, i) for i in range(4)}
    assert len(texts) == 1
    assert len(set(result.ids.pages)) == 4  # four pages, each its own page id


def test_intro_only_when_asked():
    plain = build_recipe(recipe_from_dict({"pages": [{"template": "gaps"}]}))
    assert [p.kind for p in plain.pages] == ["gaps"]
    with_intro = build_recipe(recipe_from_dict({"intro": True, "pages": [{"template": "gaps"}]}))
    assert [p.kind for p in with_intro.pages] == ["intro", "gaps"]
    assert with_intro.pages[0].layer("Practice").strokes  # a real token to try the lasso on


def test_json_recipe_and_device_override(tmp_path):
    (tmp_path / "r.json").write_text(json.dumps({"device": "pro", "pages": [{"template": "gaps"}]}))
    assert load_recipe(tmp_path / "r.json").device == "pro"
    assert load_recipe(tmp_path / "r.json", device="move").device == "move"


def test_template_file_relative_to_the_recipe(tmp_path):
    (tmp_path / "t").mkdir()
    (tmp_path / "t" / "notes.toml").write_text('name = "notes"\nhandwriting = "Writing"\n')
    (tmp_path / "r.toml").write_text('[[pages]]\ntemplate = "t/notes.toml"\n')
    doc = build_recipe(load_recipe(tmp_path / "r.toml"))
    assert doc.pages[0].handwriting == "Writing"


@pytest.mark.parametrize("data, message", [
    ({"pages": [{"template": "gaps", "wrods": ["a"]}]},
     "r.toml: pages[1] (gaps): unknown parameter 'wrods'; did you mean 'words'?"),
    ({"pages": [{"template": "gaps", "words": [1, 2]}]}, "r.toml: pages[1] (gaps): words[0]: expected text, got 1"),
    ({"pages": [{"template": "gaps", "copies": 0}]}, "r.toml: pages[1] (gaps): copies: must be at least 1 (got 0)"),
    ({"pages": [{"template": "gaps", "device": "pro"}]}, "r.toml: pages[1]: 'device' is set once for the whole document"),
    ({"pages": [{"words": ["a"]}]}, 'r.toml: pages[1]: each section needs a template = "..."'),
    ({"pages": [{"template": "gaps", "theme": "neon"}]}, "r.toml: pages[1] (gaps): theme: must be one of default"),
    ({"pages": []}, "r.toml: no [[pages]] sections"),
    ({"words": ["a"], "pages": [{"template": "gaps"}]}, "r.toml: unknown key(s) words at the top"),
    ({"device": "kindle", "pages": [{"template": "gaps"}]}, "r.toml: device: unknown device 'kindle'"),
    ({"intro": "yes", "pages": [{"template": "gaps"}]}, "r.toml: intro: expected true or false"),
])
def test_recipe_errors_point_at_the_section(data, message):
    with pytest.raises(SchemaError) as e:
        recipe_from_dict(data, "r.toml")
    assert str(e.value).startswith(message)


def test_mixed_orientations_are_refused(tmp_path):
    (tmp_path / "wide.toml").write_text('name = "wide"\norientation = "landscape"\nhandwriting = "W"\n')
    recipe = recipe_from_dict({"pages": [{"template": "gaps"}, {"template": str(tmp_path / "wide.toml")}]})
    with pytest.raises(SchemaError, match="one orientation"):
        build_recipe(recipe)


def test_document_theme_applies_where_the_template_has_it():
    recipe = recipe_from_dict({"theme": "default", "pages": [{"template": "gaps"}]})
    assert recipe.sections[0].values["theme"] == "default"
    with pytest.raises(SchemaError, match="theme 'custom' is not a theme of any template in this recipe "
                                          r"\(gaps: default, color\b[^)]*\)"):
        recipe_from_dict({"theme": "custom", "pages": [{"template": "gaps"}]})


PYTHON_TEMPLATE = '''
from rmstrokes import Layer, Page, Template


class Plain(Template):
    name = "plain"
    title = "Plain"

    def pages(self, values, ctx):
        return [Page(lambda p: None, [Layer("A")])]


TEMPLATE = Plain
'''


@pytest.mark.parametrize("named", ["plain.py", "plain"])  # by path, or found by name next to the recipe
def test_a_recipe_runs_a_python_template_only_when_allowed(tmp_path, named):
    (tmp_path / "plain.py").write_text(PYTHON_TEMPLATE)
    (tmp_path / "r.toml").write_text(f'[[pages]]\ntemplate = "{named}"\n')
    with pytest.raises(SchemaError, match=r"pages\[1\]: plain.py is a Python template file.*--allow-python"):
        load_recipe(tmp_path / "r.toml")
    recipe = load_recipe(tmp_path / "r.toml", allow_python=True)
    assert recipe.sections[0].template.name == "plain"
