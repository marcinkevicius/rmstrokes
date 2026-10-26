"""Arithmetic in template files: "W/2", "H - 40", "min(W, H) * 0.4", "{count} words".

`number` evaluates a number or an expression over named values (no attribute access, no
imports, only the functions below). `fill` replaces {name} in text; a value that is exactly
"{name}" becomes that value unchanged (a list stays a list).
"""
from __future__ import annotations

import ast
import math
import operator
import re
from typing import Any, Mapping

FUNCTIONS = {"min": min, "max": max, "abs": abs, "round": round, "floor": math.floor,
             "ceil": math.ceil, "sqrt": math.sqrt, "sin": lambda d: math.sin(math.radians(d)),
             "cos": lambda d: math.cos(math.radians(d)), "len": len,
             "longest": lambda items: max((len(str(x)) for x in items), default=0)}
_BINOPS = {ast.Add: operator.add, ast.Sub: operator.sub, ast.Mult: operator.mul,
           ast.Div: operator.truediv, ast.FloorDiv: operator.floordiv, ast.Mod: operator.mod,
           ast.Pow: operator.pow}
_UNARY = {ast.USub: operator.neg, ast.UAdd: operator.pos}
_FIELD = re.compile(r"\{(\w+)\}")


class ExprError(ValueError):
    pass


def number(value: Any, names: Mapping[str, Any], where: str = "") -> float:
    if isinstance(value, bool):
        raise ExprError(f"{where}: expected a number, got {value!r}")
    if isinstance(value, (int, float)):
        return float(value)
    if not isinstance(value, str):
        raise ExprError(f"{where}: expected a number or an expression, got {value!r}")
    try:
        tree = ast.parse(value, mode="eval")
    except SyntaxError:
        raise ExprError(f"{where}: can't read {value!r} as arithmetic") from None
    try:
        result = _eval(tree.body, names)
    except ExprError as e:
        raise ExprError(f"{where}: {value!r}: {e}") from None
    except (ArithmeticError, TypeError, ValueError) as e:
        raise ExprError(f"{where}: {value!r}: {e}") from None
    if isinstance(result, bool) or not isinstance(result, (int, float)):
        raise ExprError(f"{where}: {value!r} is not a number")
    return float(result)


def _eval(node: ast.AST, names: Mapping[str, Any]):
    if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
        return node.value
    if isinstance(node, ast.Name):
        if node.id not in names:
            raise ExprError(f"unknown name {node.id!r} (known: {', '.join(sorted(names))})")
        return names[node.id]
    if isinstance(node, ast.BinOp) and type(node.op) in _BINOPS:
        left, right = _eval(node.left, names), _eval(node.right, names)
        if isinstance(node.op, ast.Pow) and abs(right) > 16:
            raise ExprError("exponents above 16 are not allowed")
        return _BINOPS[type(node.op)](left, right)
    if isinstance(node, ast.UnaryOp) and type(node.op) in _UNARY:
        return _UNARY[type(node.op)](_eval(node.operand, names))
    if (isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id in FUNCTIONS
            and not node.keywords):
        return FUNCTIONS[node.func.id](*(_eval(a, names) for a in node.args))
    raise ExprError(f"only numbers, names, + - * / // % ** and {', '.join(FUNCTIONS)}() are allowed")


def fill(text: Any, names: Mapping[str, Any], where: str = "") -> Any:
    """{name} -> the value. "{name}" on its own -> the raw value; "{{" and "}}" are braces."""
    if not isinstance(text, str):
        return text
    whole = _FIELD.fullmatch(text)
    if whole:
        return _lookup(whole.group(1), names, where)
    parts = re.split(r"(\{\{|\}\}|\{\w+\})", text)
    out = []
    for part in parts:
        if part == "{{":
            out.append("{")
        elif part == "}}":
            out.append("}")
        elif m := _FIELD.fullmatch(part):
            v = _lookup(m.group(1), names, where)
            out.append(", ".join(map(str, v)) if isinstance(v, (list, tuple)) else str(v))
        else:
            out.append(part)
    return "".join(out)


def _lookup(key: str, names: Mapping[str, Any], where: str):
    if key not in names:
        raise ExprError(f"{where}: unknown name {{{key}}} (known: {', '.join(sorted(names))})")
    return names[key]
