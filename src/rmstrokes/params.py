"""Parameter schemas: one declaration per template parameter drives the CLI flags, the recipe
file and the docs.

    ROWS = Param("rows", "int", 8, "rows to print", min=1)
    schema = Schema([ROWS, ...])
    schema.add_arguments(parser)               # --rows N
    values = schema.validate({"rows": 6})      # recipe values: checked, defaults filled in
    schema.markdown()                          # the reference table for the docs

Types: str, int, float, bool, choice, list (of `item`), path. A default of None means "not set"
(the template decides). CLI spelling (`cli`):

  auto     by type: bool -> --x / --no-x, list -> a repeatable flag, else one value
  flag     bool, a flag that sets True (--flipped)
  negate   bool, a flag that sets False (--no-info for `info`)
  csv      list, one comma-separated value (--names "Ann,Bob")
  none     recipe only
"""
from __future__ import annotations

import argparse
import difflib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Iterable, Sequence

TYPES = ("str", "int", "float", "bool", "choice", "list", "path")
CLI_MODES = ("auto", "flag", "negate", "csv", "none")


class SchemaError(ValueError):
    pass


@dataclass(frozen=True)
class Param:
    name: str
    type: str = "str"
    default: Any = None
    help: str = ""
    choices: Sequence[str] | Callable[[], Sequence[str]] | None = None
    min: float | None = None
    max: float | None = None
    item: str = "str"                     # list item type
    flags: tuple[str, ...] = ()           # CLI flags; default --<name-with-dashes>
    cli: str = "auto"
    metavar: str | None = None
    convert: Callable[[Any], Any] | None = None   # normalise a value (raise ValueError if bad)
    check: Callable[[Any], None] | None = None     # extra check (raise ValueError)
    argtype: Callable[[str], Any] | None = None   # argparse type= (usage errors exit at parse time)
    default_text: str | None = None       # how the docs show the default

    def __post_init__(self):
        if self.type not in TYPES:
            raise ValueError(f"{self.name}: unknown type {self.type!r}; choose from {', '.join(TYPES)}")
        if self.cli not in CLI_MODES:
            raise ValueError(f"{self.name}: unknown cli mode {self.cli!r}")
        if self.type == "list" and self.item not in TYPES[:3]:
            raise ValueError(f"{self.name}: list items must be str, int or float")
        if self.type == "choice" and self.choices is None:
            raise ValueError(f"{self.name}: a choice needs choices")

    @property
    def cli_flags(self) -> tuple[str, ...]:
        if self.flags:
            return self.flags
        dashed = self.name.replace("_", "-")
        return (f"--no-{dashed}",) if self.cli == "negate" else (f"--{dashed}",)

    def choice_list(self) -> list[str] | None:
        if self.choices is None:
            return None
        return list(self.choices() if callable(self.choices) else self.choices)

    # ------------------------------------------------------------------ values

    def coerce(self, value: Any, where: str) -> Any:
        """Check and convert one value (from a recipe or the CLI)."""
        if value is None:
            return None
        try:
            if self.convert is not None:
                value = self.convert(value)
            value = self._typed(value, self.type, where)
            if self.type == "list":
                if isinstance(value, str):
                    value = [v.strip() for v in value.split(",") if v.strip()]
                if not isinstance(value, (list, tuple)):
                    raise SchemaError(f"{where}: expected a list, got {value!r}")
                value = [self._typed(v, self.item, f"{where}[{i}]") for i, v in enumerate(value)]
            self._range(value, where)
            if (choices := self.choice_list()) is not None and value not in choices:
                hint = difflib.get_close_matches(str(value), choices, 1)
                raise SchemaError(f"{where}: must be one of {', '.join(choices)} (got {value!r})"
                                  + (f"; did you mean {hint[0]!r}?" if hint else ""))
            if self.check is not None:
                self.check(value)
        except SchemaError:
            raise
        except ValueError as e:
            raise SchemaError(f"{where}: {e}") from None
        return value

    @staticmethod
    def _typed(value: Any, kind: str, where: str) -> Any:
        if kind in ("str", "choice"):
            if not isinstance(value, str):
                raise SchemaError(f"{where}: expected text, got {value!r}")
            return value
        if kind == "path":
            if not isinstance(value, (str, Path)):
                raise SchemaError(f"{where}: expected a file path, got {value!r}")
            return Path(value).expanduser()
        if kind == "bool":
            if isinstance(value, bool):
                return value
            if isinstance(value, str) and value.lower() in ("true", "yes", "on", "false", "no", "off"):
                return value.lower() in ("true", "yes", "on")
            raise SchemaError(f"{where}: expected true or false, got {value!r}")
        if kind == "int":
            if isinstance(value, bool) or not isinstance(value, (int, str, float)):
                raise SchemaError(f"{where}: expected a whole number, got {value!r}")
            try:
                f = float(value)
            except ValueError:
                raise SchemaError(f"{where}: expected a whole number, got {value!r}") from None
            if f != int(f):
                raise SchemaError(f"{where}: expected a whole number, got {value!r}")
            return int(f)
        if kind == "float":
            if isinstance(value, bool):
                raise SchemaError(f"{where}: expected a number, got {value!r}")
            try:
                return float(value)
            except (TypeError, ValueError):
                raise SchemaError(f"{where}: expected a number, got {value!r}") from None
        return value

    def _range(self, value: Any, where: str):
        values = value if isinstance(value, list) else [value]
        for v in values:
            if not isinstance(v, (int, float)):
                continue
            if self.min is not None and v < self.min:
                raise SchemaError(f"{where}: must be at least {self.min:g} (got {v:g})")
            if self.max is not None and v > self.max:
                raise SchemaError(f"{where}: must be at most {self.max:g} (got {v:g})")

    # ------------------------------------------------------------------ CLI

    def add_argument(self, parser: argparse.ArgumentParser):
        if self.cli == "none":
            return
        kw: dict[str, Any] = dict(dest=self.name, help=self.cli_help())
        if self.metavar:
            kw["metavar"] = self.metavar
        static = None if callable(self.choices) else self.choice_list()
        if self.type == "bool":
            if self.cli == "flag":
                kw.update(action="store_true", default=bool(self.default))
            elif self.cli == "negate":
                kw.update(action="store_false", default=True if self.default is None else self.default)
            else:
                kw.update(action=argparse.BooleanOptionalAction, default=self.default)
            kw.pop("metavar", None)
        elif self.type == "list" and self.cli != "csv":
            kw.update(action="append", default=None, type=self.argtype or _argtype(self.item))
            if static:
                kw["choices"] = static
        else:
            kw.update(default=self.default,
                      type=self.argtype or (str if self.cli == "csv" else _argtype(self.type)))
            if static and self.argtype is None:
                kw["choices"] = static
        parser.add_argument(*self.cli_flags, **kw)

    def cli_help(self) -> str:
        text = self.help
        if self.default not in (None, False, [], ()) and "default" not in text:
            text += f" (default: {self.default_text or _show(self.default)})"
        return text.replace("%", "%%")


def _argtype(kind: str):
    return {"int": int, "float": float, "path": Path}.get(kind, str)


def _show(v: Any) -> str:
    if isinstance(v, bool):
        return "on" if v else "off"
    if isinstance(v, (list, tuple)):
        return ", ".join(map(str, v))
    return str(v)


@dataclass(frozen=True)
class Schema:
    params: tuple[Param, ...] = ()
    check: Callable[[dict], None] | None = field(default=None, compare=False)  # cross-parameter

    def __post_init__(self):
        names = [p.name for p in self.params]
        if dup := {n for n in names if names.count(n) > 1}:
            raise ValueError(f"parameters declared twice: {sorted(dup)}")

    def __iter__(self):
        return iter(self.params)

    def __add__(self, other: Schema) -> Schema:
        return Schema((*self.params, *other.params), self.check or other.check)

    def names(self) -> list[str]:
        return [p.name for p in self.params]

    def get(self, name: str) -> Param:
        return next(p for p in self.params if p.name == name)

    def defaults(self) -> dict[str, Any]:
        return {p.name: p.default for p in self.params}

    def validate(self, values: dict[str, Any], where: str = "") -> dict[str, Any]:
        """Check recipe or CLI values: unknown names, types, ranges, choices. Returns every
        parameter, defaults filled in. Errors read "<where>: <param>: <problem>"."""
        prefix = f"{where}: " if where else ""
        known = {p.name: p for p in self.params}
        for key in values:
            if key not in known:
                hint = difflib.get_close_matches(key, list(known), 1)
                raise SchemaError(f"{prefix}unknown parameter {key!r}"
                                  + (f"; did you mean {hint[0]!r}?" if hint else "")
                                  + f" (known: {', '.join(known)})")
        out = {}
        for p in self.params:
            value = values.get(p.name, p.default)
            out[p.name] = p.coerce(value, f"{prefix}{p.name}") if value is not None else None
        if self.check is not None:
            try:
                self.check(out)
            except SchemaError as e:
                raise SchemaError(f"{prefix}{e}") from None
            except ValueError as e:
                raise SchemaError(f"{prefix}{e}") from None
        return out

    def add_arguments(self, parser: argparse.ArgumentParser, skip: Iterable[str] = ()):
        for p in self.params:
            if p.name not in skip:
                p.add_argument(parser)

    def from_args(self, args: argparse.Namespace) -> dict[str, Any]:
        """The parsed CLI values, as validate() takes them (unset lists left out)."""
        out = {}
        for p in self.params:
            if p.cli != "none" and hasattr(args, p.name):
                v = getattr(args, p.name)
                if not (p.type == "list" and v is None):
                    out[p.name] = v
        return out

    # ------------------------------------------------------------------ docs

    def markdown(self) -> str:
        rows = ["| Parameter | CLI | Type | Default | Meaning |", "|---|---|---|---|---|"]
        for p in self.params:
            kind = p.type
            if p.type == "list":
                kind = f"list of {p.item}"
            elif (choices := p.choice_list()) is not None and not callable(p.choices):
                kind = " \\| ".join(f"`{c}`" for c in choices)
            elif callable(p.choices):
                kind = "name"
            if p.min is not None or p.max is not None:
                lo = "" if p.min is None else f"{p.min:g}"
                hi = "" if p.max is None else f"{p.max:g}"
                kind += f" ({lo}..{hi})" if lo and hi else (f" (≥ {lo})" if lo else f" (≤ {hi})")
            cli = "–" if p.cli == "none" else ", ".join(f"`{f}`" for f in p.cli_flags)
            if p.type == "bool" and p.cli == "auto":
                cli = f"`--{p.name.replace('_', '-')}` / `--no-{p.name.replace('_', '-')}`"
            default = p.default_text or ("–" if p.default is None else f"`{_toml(p.default)}`")
            meaning = p.help.replace("|", "\\|")
            rows.append(f"| `{p.name}` | {cli} | {kind} | {default} | {meaning} |")
        return "\n".join(rows)

    def recipe_example(self) -> str:
        """The parameters as recipe lines with their defaults (unset ones commented out)."""
        lines = []
        for p in self.params:
            if p.default is None:
                lines.append(f"# {p.name} = ...")
            else:
                lines.append(f"{p.name} = {_toml(p.default)}")
        return "\n".join(lines)


def _toml(v: Any) -> str:
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, str):
        return '"' + v.replace("\\", "\\\\").replace('"', '\\"') + '"'
    if isinstance(v, Path):
        return _toml(str(v))
    if isinstance(v, (list, tuple)):
        return "[" + ", ".join(_toml(x) for x in v) + "]"
    return str(v)
