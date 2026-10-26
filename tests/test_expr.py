"""Arithmetic and text substitution in template files."""
import pytest

from rmstrokes.expr import ExprError, fill, number

NAMES = {"W": 150.0, "H": 200.0, "n": 3, "groups": ["a", "b"], "who": "Ann"}


def test_numbers_and_expressions():
    assert number(5, NAMES) == 5.0
    assert number("W / 2 - 10", NAMES) == 65.0
    assert number("min(W, H) * 0.5 + len(groups)", NAMES) == 77.0
    assert number("-n ** 2 + 30 // 4 % 5", NAMES) == pytest.approx(-9 + 2)
    assert number("round(cos(0) * 10)", NAMES) == 10.0


@pytest.mark.parametrize("expr, message", [
    ("W.__class__", "only numbers"),
    ("__import__('os')", "only numbers"),
    ("lambda: 1", "only numbers"),
    ("X + 1", "unknown name 'X'"),
    ("2 ** 100", "exponents"),
    ("W +", "can't read"),
    ("who", "is not a number"),
    ("1 / 0", "division"),
])
def test_unsafe_or_wrong_expressions_are_refused(expr, message):
    with pytest.raises(ExprError, match=message):
        number(expr, NAMES, "x")


def test_fill():
    assert fill("Hi {who}, {n} words", NAMES) == "Hi Ann, 3 words"
    assert fill("{groups}", NAMES) == ["a", "b"]           # a whole field keeps its type
    assert fill("groups: {groups}", NAMES) == "groups: a, b"
    assert fill("{{literal}}", NAMES) == "{literal}"
    assert fill(7, NAMES) == 7
    with pytest.raises(ExprError, match="unknown name {nobody}"):
        fill("{nobody}", NAMES, "x")
