"""The gallery: config resolution, the dry run, a small build with its contact sheet, and template
files found by name (registered, or next to a recipe)."""
import subprocess
import sys
from pathlib import Path

import pytest

from rmstrokes import cli, gallery
from rmstrokes.params import SchemaError
from rmstrokes.templates import available_templates, get_template

EXAMPLES = Path(__file__).resolve().parents[1] / "examples"

COLOR_TEMPLATE = '''
from rmstrokes import Layer, Page, Template


class Tinted(Template):
    name = "tinted"
    title = "Tinted"
    color_theme = "tint"

    def themes(self):
        return ["plain", "tint"]

    default_theme = "plain"

    def pages(self, values, ctx):
        def draw(p):
            p.c.drawString(40, 40, f"theme {ctx.theme}")
        return [Page(draw=draw, layers=[Layer("Tokens", [])], kind=self.name, meta={"theme": ctx.theme})]


TEMPLATE = Tinted()
'''


def write_config(folder: Path, body: str) -> Path:
    (folder / "tinted.py").write_text(COLOR_TEMPLATE)
    config = folder / "gallery.toml"
    config.write_text(f'devices = ["rm2"]\ngroups = ["mine", "templates"]\n'
                      f'templates = [{{ path = "tinted.py", group = "mine" }}]\n{body}')
    return config


def test_every_template_gets_a_default_entry(tmp_path):
    g = gallery.load_gallery(write_config(tmp_path, ""))
    templates = [j for j in g.jobs if j.entry.kind == "template"]
    assert {j.entry.template for j in templates} == expected()
    assert all(j.entry.intro for j in templates)
    assert g.groups[0] == "mine"  # the config's order


def expected() -> set[str]:
    """Installed and built-in templates, and the config's file; not what other tests registered
    in this process, nor template files another config listed."""
    from rmstrokes.templates import template_origin
    return {n for n in available_templates() if template_origin(n) in ("installed", "builtin")} | {"tinted"}


def test_devices_and_move(tmp_path):
    config = write_config(tmp_path, "")
    config.write_text(config.read_text().replace('devices = ["rm2"]', 'devices = ["rm2", "paper-pro"]'))
    assert [d.key for d in gallery.load_gallery(config).devices] == ["rm2", "pro"]
    assert [d.key for d in gallery.load_gallery(config, with_move=True).devices] == ["rm2", "pro", "move"]


def test_dry_run_lists_every_template_and_example(tmp_path, capsys):
    config = write_config(tmp_path, f'''
[[examples]]
group = "templates"
name = "reading"
recipe = "{(EXAMPLES / "reading.toml").as_posix()}"

[[examples]]
group = "mine"
name = "many-words"
template = "gaps"
words = ["one", "two", "three", "four", "five", "six", "seven", "eight"]
''')
    assert cli.main(["gallery", str(config), "--dry-run", "--with-move"]) == 0
    out = capsys.readouterr().out
    for name in expected():
        assert f"template: {name}" in out
    assert "reading" in out and "many-words" in out
    assert "[unverified device]" in out  # pro and move
    assert not any(tmp_path.glob("**/*.rmdoc"))


@pytest.mark.parametrize("body, message", [
    ('[[examples]]\ngroup = "mine"\nname = "x"\ntemplate = "nope"\n', "unknown template 'nope'"),
    ('[[examples]]\ngroup = "mine"\nname = "x"\ntemplate = "gaps"\nwords = [1]\n', "words"),
    ('[[examples]]\ngroup = "mine"\nname = "x"\nrecipe = "missing.toml"\n', "not found"),
    ('[[examples]]\ngroup = "mine"\nname = "x"\ncommand = ["no-such-tool"]\n', "not installed"),
    ('[[examples]]\ngroup = "mine"\nname = "x"\n', "exactly one of"),
    ('[[examples]]\ngroup = "mine"\nname = "tinted-default"\ntemplate = "gaps"\n', "already taken"),
    ('colour = 1\n', "unknown key"),
])
def test_config_errors(tmp_path, body, message):
    with pytest.raises(SchemaError, match=message):
        gallery.load_gallery(write_config(tmp_path, body))


def test_build_writes_rmdoc_pdf_png_and_index(tmp_path):
    pytest.importorskip("pypdfium2")
    config = write_config(tmp_path, '''
[[examples]]
group = "mine"
name = "via-command"
title = "Made by a console script"
command = ["rmstrokes", "make", "gaps", "--words", "sun", "--words", "rain"]
color_args = ["--theme", "default"]
''')
    g = gallery.load_gallery(config, only=["mine"])
    out = tmp_path / "out"
    results = gallery.run_gallery(g, out, log=lambda line: None)
    assert [b.error for b in results] == [None] * len(results)
    for b in results:
        assert set(b.files) == {"rmdoc", "pdf", "png"}
        assert all((out / p).is_file() for p in b.files.values())
        assert b.files["png"].parts[:2] == ("mine", "rm2")
    index = (out / "index.html").read_text()
    assert "Made by a console script" in index and "mine/rm2/via-command.png" in index
    with pytest.raises(ValueError, match="never writes over"):
        gallery.run_gallery(g, out)


def test_a_failure_is_reported_not_raised(tmp_path, monkeypatch):
    g = gallery.load_gallery(write_config(tmp_path, ""), only=["mine"])
    monkeypatch.setattr(gallery, "build_document", lambda *a, **k: 1 / 0)
    [built] = gallery.run_gallery(g, tmp_path / "out", log=lambda line: None)
    assert "ZeroDivisionError" in built.error
    assert "ZeroDivisionError" in (tmp_path / "out" / "index.html").read_text()


def test_colour_devices_get_the_colour_theme(tmp_path):
    config = write_config(tmp_path, '''
[[examples]]
group = "mine"
name = "pinned"
template = "tinted"
theme = "plain"
''')
    (tmp_path / "recipe.toml").write_text('[[pages]]\ntemplate = "tinted"\ntheme = "plain"\n')
    pro = gallery.DEVICES["pro"]
    g = gallery.load_gallery(config, only=["mine"])
    default, pinned = (j.entry for j in g.jobs)
    assert gallery.template_section(default, pro, tmp_path).values["theme"] == "tint"
    assert gallery.template_section(default, gallery.DEVICES["rm2"], tmp_path).values["theme"] == "plain"
    assert gallery.template_section(pinned, pro, tmp_path).values["theme"] == "plain"  # set by the entry
    entry = gallery.parse_entry({"group": "mine", "name": "r", "recipe": "recipe.toml"}, "test", tmp_path)
    assert gallery.load_recipe_for(entry, pro).sections[0].values["theme"] == "tint"
    assert gallery.load_recipe_for(entry, gallery.DEVICES["rm2"]).sections[0].values["theme"] == "plain"


def test_each_device_gets_its_design_theme(tmp_path):
    config = write_config(tmp_path, '[[examples]]\ngroup = "templates"\nname = "grey"\ntemplate = "gaps"\n'
                                    'theme = "default"\n')
    g = gallery.load_gallery(config, only=["templates"])
    entries = {j.entry.name: j.entry for j in g.jobs}
    rm2, pro = gallery.DEVICES["rm2"], gallery.DEVICES["pro"]
    assert gallery.template_section(entries["gaps-default"], rm2, tmp_path).values["theme"] == "default"
    assert gallery.template_section(entries["gaps-default"], pro, tmp_path).values["theme"] == "color"
    assert gallery.template_section(entries["grey"], pro, tmp_path).values["theme"] == "default"  # pinned


def test_the_specimen_is_in_the_gallery(tmp_path):
    pytest.importorskip("pypdfium2")
    config = write_config(tmp_path, "")
    config.write_text(config.read_text().replace('devices = ["rm2"]', 'devices = ["rm2", "pro"]'))
    g = gallery.load_gallery(config, only=[gallery.DESIGN_APP])
    assert [(j.entry.kind, j.device.key) for j in g.jobs] == [("specimen", "rm2"), ("specimen", "pro")]
    out = tmp_path / "out"
    results = gallery.run_gallery(g, out, log=lambda line: None)
    assert [b.error for b in results] == [None, None]
    assert all(b.pages > 1 and set(b.files) == {"rmdoc", "pdf", "png"} for b in results)
    assert "design-system/pro/specimen.png" in (out / "index.html").read_text()


def test_default_out_is_new_each_time(tmp_path):
    config = write_config(tmp_path, "")
    first = gallery.default_out(config, tmp_path / "runs")
    first.mkdir(parents=True)
    second = gallery.default_out(config, tmp_path / "runs")
    assert second != first and second.name.startswith(first.name)


def test_a_recipe_finds_a_template_file_next_to_it_by_name(tmp_path):
    (tmp_path / "my_page.toml").write_text((EXAMPLES / "templates" / "sorting.toml").read_text()
                                           .replace('name = "sorting"', 'name = "my-page"', 1))
    assert get_template("my-page", tmp_path).name == "my-page"
    with pytest.raises(SchemaError, match="unknown template"):
        get_template("other-page", tmp_path)


def test_a_misnamed_template_file_is_refused(tmp_path):
    (tmp_path / "wrong_name.toml").write_text((EXAMPLES / "templates" / "sorting.toml").read_text())
    with pytest.raises(SchemaError, match="defines template 'sorting'"):
        get_template("wrong-name", tmp_path)


@pytest.mark.parametrize("recipe", sorted(EXAMPLES.glob("*.toml")), ids=lambda p: p.name)
def test_rmstrokes_build_runs_the_example_recipes(recipe, tmp_path):
    """As a user would: the command line, with nothing registered first."""
    r = subprocess.run([sys.executable, "-m", "rmstrokes.cli", "build", str(recipe), "-o", str(tmp_path)],
                       capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    assert len(list(tmp_path.glob("*.rmdoc"))) == 1


def test_the_repository_gallery_resolves_without_other_packages():
    """gallery.toml next to this package lists only this repository's own examples; installed templates
    are found through the registry, never named in it."""
    config = EXAMPLES.parent / "gallery.toml"
    g = gallery.load_gallery(config, with_move=True)
    assert [d.key for d in g.devices] == ["rm2", "pro", "move"]
    listed = {j.entry.recipe for j in g.jobs if j.entry.kind == "recipe"}
    recipes = {p.resolve() for p in [*EXAMPLES.glob("*.toml"), *EXAMPLES.glob("*.json"),
                                     *EXAMPLES.glob("*/*.toml")] if p.parent.name != "templates"}
    assert recipes <= listed, f"recipes missing from gallery.toml: {sorted(map(str, recipes - listed))}"
    assert not any(j.entry.kind == "command" for j in g.jobs)
    names = {j.entry.template for j in g.jobs if j.entry.kind == "template"}
    assert {"gaps", "sorting"} <= names
