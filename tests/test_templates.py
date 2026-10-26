"""Templates as data (TOML): the built-in fill-in-the-gaps exercise, and template files."""
import pytest

from rmstrokes.datatemplate import load_template_file
from rmstrokes.devices import DEVICES, get_device
from rmstrokes.layers import Document
from rmstrokes.params import SchemaError
from rmstrokes.templates import BUILTIN_DIR, Context, available_templates, get_template, template_origin
from strokes_helpers import pdf_text

LANDSCAPE = '''
name = "columns"
title = "Column sheet"
orientation = "landscape"
handwriting = "Writing"

[params.groups]
type = "int"
default = 2
min = 1

[[background]]
type = "text"
text = "Columns"
x = 10
y = 15

[[background]]
type = "rect"
repeat = "groups"
x = "10 + i * 60"
y = 25
w = 55
h = 40
'''

TOKENS = '''
name = "demo"
title = "Token demo"

[params.count]
type = "int"
default = 5
min = 1

[params.names]
type = "list"
default = []

[params.circle]
type = "bool"
default = false

[intro]
title = "Moving tokens"
steps = ["Lasso a token and drag it."]

[[background]]
type = "circle"
cx = "W / 2"
cy = "H / 2"
r = 40
style = "dashed"

[[background]]
type = "text"
text = "Only with a circle"
when = "circle"
x = 10
y = 10

[tokens.dot]
shape = "icon.svg"
size = 9
style = "filled"
name_tag = { width = 18, height = 6 }

[tokens.pin]
shape = "pin"
size = 6
label = "{item}"

[[trays]]
name = "start"
token = "dot"
count = "count"
x = 10
y = "H - 50"
w = "W - 20"
h = 40

[[trays]]
name = "middle"
token = "pin"
count = "len(names)"
labels = "{names}"
x = "W / 2 - 40"
y = "H / 2 - 10"
w = 80
h = 20
columns = 3
when = "circle"

[[layers]]
name = "Dots"
trays = ["start"]

[[layers]]
name = "Pins"
trays = ["middle"]
'''


def build(template, values=None, device="rm2"):
    v = template.validate({**(values or {}), "device": device})
    return template.pages(v, Context(get_device(device), v["theme"]))


def test_builtins_are_listed():
    names = available_templates()
    assert "gaps" in names
    assert {f.stem for f in BUILTIN_DIR.glob("*.toml")} == {"gaps"}  # the one built-in
    assert template_origin("gaps") == "builtin"


@pytest.mark.parametrize("device", list(DEVICES))
def test_gaps_builds_on_every_device(device):
    (page,) = build(get_template("gaps"), device=device)
    assert [layer.name for layer in page.layers] == ["Words"] and page.handwriting == "Notes"
    assert page.strokes, "the words start in their bank"
    text = pdf_text(Document(get_device(device), [page]).render_pdf())
    assert "Fill in the gaps" in text and "Water in lakes" in text and "WORDS" in text.upper()


def test_gaps_has_a_tag_per_word_and_gaps_a_tag_fits_on():
    t = get_template("gaps")
    words = ["alpha", "beta", "gamma", "delta", "epsilon", "zeta", "eta"]
    (page,) = build(t, {"words": words, "text": "One ___ two ___.\nThree ___ four.", "title": "Greek"})
    four = build(t, {"words": words[:4]})[0]
    assert len(four.layer("Words").strokes) < len(page.layer("Words").strokes)
    text = pdf_text(Document(DEVICES["rm2"], [page]).render_pdf())
    assert "Greek" in text and "One" in text and "Three" in text and "four." in text
    # Every tag is as wide as the longest word needs, and every gap a little wider.
    names = t._names(t.validate({"words": words}), DEVICES["rm2"], "x")
    assert names["tag_w"] == pytest.approx(10 + 2.4 * len("epsilon"))
    assert names["rows"] * names["cols"] >= len(words)


def test_gaps_intro_shows_the_first_word():
    t = get_template("gaps")
    spec = t.intro_spec(t.validate({"words": ["sun", "rain"]}))
    assert spec.thing == "word" and spec.layer == "Words"
    assert spec.token(DEVICES["rm2"], 20).strokes  # the "sun" tag, drawn


def test_a_passage_that_doesnt_fit_says_so():
    t = get_template("gaps")
    with pytest.raises(SchemaError, match=r"passage\): the text needs \d+ lines"):
        build(t, {"text": "word ___ " * 400}, device="move")


def test_trays_are_grids(tmp_path):
    (tmp_path / "hex.toml").write_text(TOKENS.replace("columns = 3", 'kind = "hexagon"'))
    with pytest.raises(SchemaError, match="kind must be rect, not 'hexagon'"):
        load_template_file(tmp_path / "hex.toml")
    (tmp_path / "dots.toml").write_text(TOKENS.replace("columns = 3", "sparkles = true"))
    with pytest.raises(SchemaError, match=r"unknown key\(s\) sparkles"):
        load_template_file(tmp_path / "dots.toml")


def test_let_names(tmp_path):
    (tmp_path / "t.toml").write_text(LANDSCAPE + '\n[let]\nwide = "W - 20"\nhalf = "wide / 2"\n')
    t = load_template_file(tmp_path / "t.toml")
    names = t._names(t.validate({}), DEVICES["rm2"], "x")
    assert names["half"] == pytest.approx((names["W"] - 20) / 2)
    (tmp_path / "u.toml").write_text(LANDSCAPE + '\n[let]\ngroups = 3\n')
    with pytest.raises(SchemaError, match="let.groups: 'groups' is already a parameter"):
        load_template_file(tmp_path / "u.toml")


def test_safe_area_names(tmp_path):
    (tmp_path / "t.toml").write_text(LANDSCAPE)
    t = load_template_file(tmp_path / "t.toml")
    names = t._names(t.validate({}), DEVICES["rm2"], "x")
    assert (names["safe_x"], names["safe_y"]) == pytest.approx((14, 8))  # the toolbar strip, the margin
    assert names["safe_x"] + names["safe_w"] + 8 == pytest.approx(names["W"])  # landscape: W is the long side
    assert names["safe_y"] + names["safe_h"] + 8 == pytest.approx(names["H"])
    (tmp_path / "u.toml").write_text(LANDSCAPE + '\n[let]\nsafe_w = 3\n')
    with pytest.raises(SchemaError, match="'safe_w' is already a parameter or a built-in name"):
        load_template_file(tmp_path / "u.toml")


def test_template_file_with_svg_tokens_two_trays_and_conditions(tmp_path, icon):
    (tmp_path / "demo.toml").write_text(TOKENS)
    (tmp_path / "icon.svg").write_text(icon.read_text())
    t = load_template_file(tmp_path / "demo.toml")
    assert t.intro.title == "Moving tokens" and t.intro.layer == "Pins"
    plain = build(t)[0]
    assert plain.layer("Pins").strokes == [] and plain.layer("Dots").strokes
    circled = build(t, {"circle": True, "names": ["A", "B", "C"]})[0]
    assert circled.layer("Pins").strokes
    assert "Only with a circle" in pdf_text(Document(DEVICES["rm2"], [circled]).render_pdf())
    assert "Only with a circle" not in pdf_text(Document(DEVICES["rm2"], [plain]).render_pdf())


def test_landscape_template_and_repeat(tmp_path):
    (tmp_path / "columns.toml").write_text(LANDSCAPE)
    t = get_template(str(tmp_path / "columns.toml"))
    (page,) = build(t, {"groups": 3})
    assert page.landscape and page.handwriting == "Writing" and not page.layers


@pytest.mark.parametrize("change, message", [
    (("[params.groups]", "[params.device]"), "'device' is a common parameter"),
    (('type = "rect"', 'type = "blob"'), "background 2: type must be one of"),
    (('orientation = "landscape"', 'orientation = "sideways"'), "orientation must be"),
    (('handwriting = "Writing"', 'colour = "red"'), "unknown key(s) colour"),
    (("default = 2", 'default = "two"'), "params.groups: default: expected a whole number"),
])
def test_template_file_errors(tmp_path, change, message):
    (tmp_path / "bad.toml").write_text(LANDSCAPE.replace(*change))
    with pytest.raises(SchemaError, match=__import__("re").escape(message)):
        load_template_file(tmp_path / "bad.toml")


def test_build_time_errors_name_the_element(tmp_path, icon):
    (tmp_path / "icon.svg").write_text(icon.read_text())
    (tmp_path / "t.toml").write_text(TOKENS.replace('h = 40', 'h = 4'))
    with pytest.raises(SchemaError, match=r"trays\[1\]: 5 dot tokens \(.* mm each, with padding\) don.t fit"):
        build(load_template_file(tmp_path / "t.toml"))
    (tmp_path / "u.toml").write_text(LANDSCAPE.replace('x = "10 + i * 60"', 'x = "10 + j"'))
    with pytest.raises(SchemaError, match=r"background 2 \(rect\): x: '10 \+ j': unknown name 'j'"):
        build(load_template_file(tmp_path / "u.toml"))
    (tmp_path / "v.toml").write_text(TOKENS.replace('token = "pin"', 'token = "ghost"'))
    with pytest.raises(SchemaError, match="token 'ghost' is not defined"):
        load_template_file(tmp_path / "v.toml")


def test_unknown_template():
    with pytest.raises(SchemaError, match="unknown template 'nope'; available: .*gaps"):
        get_template("nope")
    with pytest.raises(SchemaError, match="not found"):
        get_template("missing/file.toml")


def test_python_template_file_needs_a_template(tmp_path):
    bad = tmp_path / "nothing.py"
    bad.write_text("X = 1\n")
    with pytest.raises(SchemaError, match="must define TEMPLATE"):
        get_template(str(bad))
    good = tmp_path / "mine.py"
    good.write_text("from rmstrokes import Template\n\nclass Mine(Template):\n    name = 'mine'\n\nTEMPLATE = Mine\n")
    assert get_template("mine.py", base=tmp_path).name == "mine"
    with pytest.raises(SchemaError, match="not found"):
        get_template("missing.py", base=tmp_path)


@pytest.mark.parametrize("shape", ["../outside.svg", "/tmp/outside.svg", "sub/../../outside.svg"])
def test_a_template_reads_svgs_only_from_its_own_folder(tmp_path, icon, shape):
    folder = tmp_path / "t"
    folder.mkdir()
    (tmp_path / "outside.svg").write_text(icon.read_text())
    (folder / "t.toml").write_text(TOKENS.replace('shape = "icon.svg"', f'shape = "{shape}"'))
    (folder / "icon.svg").write_text(icon.read_text())
    t = load_template_file(folder / "t.toml")
    with pytest.raises(SchemaError, match="must be a file in the template's own folder"):
        build(t, {})


def test_a_template_reads_svgs_in_a_subfolder(tmp_path, icon):
    (tmp_path / "art").mkdir()
    (tmp_path / "art" / "icon.svg").write_text(icon.read_text())
    (tmp_path / "t.toml").write_text(TOKENS.replace('shape = "icon.svg"', 'shape = "art/icon.svg"'))
    assert build(load_template_file(tmp_path / "t.toml"), {})[0].layer("Dots").strokes
