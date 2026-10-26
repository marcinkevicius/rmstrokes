"""Parameter schemas: validation errors that say where and what, and the CLI/docs they drive."""
import argparse

import pytest

from rmstrokes.params import Param, Schema, SchemaError

SCHEMA = Schema((
    Param("rows", "int", 8, "rows to print", min=1, max=12),
    Param("style", "choice", "outline", "fill style", choices=("outline", "filled")),
    Param("names", "list", [], "titles", cli="csv"),
    Param("positions", "list", [], "one per page", flags=("--pos",)),
    Param("info", "bool", True, "a header strip", cli="negate"),
    Param("flipped", "bool", False, "turn it", cli="flag"),
    Param("tray", "bool", None, "trays"),
    Param("gap", "float", 1.5, "gap in mm", min=0),
    Param("title", "str", None, "heading"),
))


def test_defaults_are_filled_in():
    v = SCHEMA.validate({})
    assert v == {"rows": 8, "style": "outline", "names": [], "positions": [], "info": True,
                 "flipped": False, "tray": None, "gap": 1.5, "title": None}


@pytest.mark.parametrize("values, message", [
    ({"row": 3}, "sheet: unknown parameter 'row'; did you mean 'rows'? (known: rows, style, names,"),
    ({"rows": 0}, "sheet: rows: must be at least 1 (got 0)"),
    ({"rows": 13}, "sheet: rows: must be at most 12 (got 13)"),
    ({"rows": "six"}, "sheet: rows: expected a whole number, got 'six'"),
    ({"rows": 2.5}, "sheet: rows: expected a whole number, got 2.5"),
    ({"rows": True}, "sheet: rows: expected a whole number, got True"),
    ({"style": "filed"}, "sheet: style: must be one of outline, filled (got 'filed'); did you mean 'filled'?"),
    ({"names": [1, "b"]}, "sheet: names[0]: expected text, got 1"),
    ({"info": "maybe"}, "sheet: info: expected true or false, got 'maybe'"),
    ({"gap": -1}, "sheet: gap: must be at least 0 (got -1)"),
    ({"title": 5}, "sheet: title: expected text, got 5"),
])
def test_errors_name_the_parameter_and_the_problem(values, message):
    with pytest.raises(SchemaError) as e:
        SCHEMA.validate(values, "sheet")
    assert str(e.value).startswith(message)


def test_conversions():
    v = SCHEMA.validate({"rows": "6", "names": "Ann, Bob", "info": "off", "gap": 2})
    assert v["rows"] == 6 and v["names"] == ["Ann", "Bob"] and v["info"] is False and v["gap"] == 2.0


def test_checks_and_cross_checks():
    def no_odd(v):
        if v % 2:
            raise ValueError("must be even")

    def cross(values):
        if values["a"] > values["b"]:
            raise ValueError("a can't be more than b")
    s = Schema((Param("a", "int", 2, check=no_odd), Param("b", "int", 4)), check=cross)
    with pytest.raises(SchemaError, match="^x: a: must be even$"):
        s.validate({"a": 3}, "x")
    with pytest.raises(SchemaError, match="^x: a can't be more than b$"):
        s.validate({"a": 6}, "x")


def test_cli_flags_come_from_the_schema():
    ap = argparse.ArgumentParser()
    SCHEMA.add_arguments(ap)
    args = ap.parse_args(["--rows", "6", "--names", "A,B", "--pos", "x", "--pos", "y", "--no-info",
                          "--flipped", "--no-tray", "--style", "filled"])
    v = SCHEMA.validate(SCHEMA.from_args(args))
    assert v["rows"] == 6 and v["names"] == ["A", "B"] and v["positions"] == ["x", "y"]
    assert v["info"] is False and v["flipped"] is True and v["tray"] is False and v["style"] == "filled"
    assert SCHEMA.validate(SCHEMA.from_args(ap.parse_args([]))) == SCHEMA.validate({})
    with pytest.raises(SystemExit):
        ap.parse_args(["--style", "glitter"])  # static choices are usage errors


def test_docs_and_recipe_example():
    md = SCHEMA.markdown()
    assert "| `rows` | `--rows` | int (1..12) | `8` | rows to print |" in md
    assert "`--no-info`" in md and "`--tray` / `--no-tray`" in md and "`outline` \\| `filled`" in md
    example = SCHEMA.recipe_example()
    assert 'rows = 8' in example and '# title = ...' in example and 'names = []' in example


def test_declaration_errors():
    with pytest.raises(ValueError, match="unknown type"):
        Param("x", "colour")
    with pytest.raises(ValueError, match="needs choices"):
        Param("x", "choice")
    with pytest.raises(ValueError, match="declared twice"):
        Schema((Param("x"), Param("x")))
