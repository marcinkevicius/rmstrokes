"""Templates as data: a TOML file describes the parameters, the background, the tokens and the
trays they start in. See docs/templates.md for the full reference; in short:

    name = "example"
    title = "Example"
    orientation = "portrait"            # or "landscape"

    [params.tokens]                     # parameters: the same schema as Python templates
    type = "int"
    default = 8
    min = 1
    help = "how many tokens"

    [let]                               # named numbers, worked out once per page, in order
    box_h = "(H - 90) / 2"

    [intro]                             # this template's part of the intro page
    title = "Sorting"
    steps = ["Write a name in each tag.", "Lasso a token and drag it into a group."]

    [[background]]                      # printed on the PDF, in order
    type = "rect"
    x = 15                              # lengths in mm; W and H are the page size in mm
    y = 30
    w = "W - 30"
    h = "box_h"

    [tokens.dot]                        # what a token looks like
    shape = "circle"
    size = 10
    number = "n"                        # n = 1, 2, ... per slot
    name_tag = { width = 22, height = 7 }

    [[trays]]                           # where tokens start: a grid of slots
    name = "start"
    token = "dot"
    count = "tokens"
    x = 15
    y = "H - 50"
    w = "W - 30"
    h = 40

    [[layers]]                          # stroke layers, bottom to top
    name = "Tokens"
    trays = ["start"]

Numbers may be expressions over W, H, the parameters and the [let] names (expr.py); text may
contain {param}.
Fonts are text roles of the theme's style (`font = "caption"`, see design.py) or font file names;
colours are palette tokens (`color = "muted"`, `fill = "accent-1-tint"`) or "#RRGGBB".
An element with `repeat = <count or list parameter>` is drawn once per item, with i (from 0),
n (from 1) and item (the list entry) available; `when = "<bool parameter>"` makes it optional.
"""
from __future__ import annotations

import math
import re
import tomllib
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any, Callable

from reportlab.lib.colors import HexColor

from . import fonts
from .design import ROLES, Style
from .expr import ExprError, fill, number
from .fields import FieldStyle, WriteIn, draw_write_in
from .geometry import Rect, grid_cells, page_size
from .intro import IntroSpec, token_maker
from .layers import Layer, Page
from .params import TYPES, Param, Schema, SchemaError
from .pdf import Painter
from .templates import COMMON_NAMES, Context, Template
from .tokens import NameTag, Placement, Token, TokenArt, token_art

TOP_KEYS = {"name", "title", "description", "orientation", "params", "let", "intro", "background", "tokens",
            "trays", "layers", "handwriting", "handwriting_on_top", "active"}
ELEMENTS = ("text", "passage", "line", "rect", "circle", "sectors", "write-in", "lines")
PARAM_KEYS = {"type", "default", "help", "min", "max", "choices", "item", "metavar"}
TOKEN_KEYS = {"shape", "size", "height", "style", "pen", "label", "number", "icon", "name_tag", "svg_units"}
TAG_KEYS = {"width", "height", "side", "style", "overlap", "knockout"}
TRAY_KEYS = {"name", "token", "count", "kind", "x", "y", "w", "h", "gap", "columns", "frame", "label", "labels",
             "pad", "when"}
SLOT_PAD_MM = 2.0
GAP = re.compile(r"(_{3,})")  # a gap in a passage: three or more underscores
# Names every expression has; [let] can't reuse them.
BUILTIN_NAMES = ("W", "H", "safe_x", "safe_y", "safe_w", "safe_h", "i", "n", "item", "document")


def load_template_file(path: Path) -> DataTemplate:
    path = Path(path)
    try:
        data = tomllib.loads(path.read_text(encoding="utf-8"))
    except tomllib.TOMLDecodeError as e:
        raise SchemaError(f"{path.name}: {e}") from None
    return DataTemplate(data, path)


def _err(where: str, msg: str) -> SchemaError:
    return SchemaError(f"{where}: {msg}")


def _unknown(table: dict, known: set[str], where: str):
    if bad := sorted(set(table) - known):
        raise _err(where, f"unknown key(s) {', '.join(bad)} (known: {', '.join(sorted(known))})")


@dataclass(frozen=True)
class TrayLayout:
    """A tray worked out in page px: its area, a (box, rotation) cell per token (rotation in
    degrees clockwise about the box centre) and each token's art."""

    name: str
    area: Rect
    cells: tuple[tuple[Rect, float], ...]
    arts: tuple[TokenArt, ...]
    label: str = ""
    tokens: tuple[Token, ...] = ()  # each slot's token, as its art was made from

    def placements(self, layer: str) -> list[Placement]:
        return [Placement(layer, token, art, box, rotation)
                for (box, rotation), art, token in zip(self.cells, self.arts, self.tokens)]

    def strokes(self) -> list:
        """Each token in its cell, token by token, so each stays one contiguous cluster."""
        return [s for (box, rotation), art in zip(self.cells, self.arts) for s in art.placed(*box.center, rotation)]


@dataclass
class _Ops:
    """Background drawing, resolved to numbers: a list of draw calls."""

    calls: list[Callable[[Painter], None]] = field(default_factory=list)
    fonts: set[str] = field(default_factory=set)
    areas: list[tuple[str, Rect]] = field(default_factory=list)  # (element type, box): Page.meta["areas"]

    def __call__(self, p: Painter):
        for call in self.calls:
            call(p)


class DataTemplate(Template):
    """A template read from TOML. Trays here are grids of slots (`kind = "rect"`); a subclass can
    add tray kinds and keys (`tray_kinds`, `tray_keys`) and override `_tray_cells` and `_tray_call`
    to lay them out and draw them differently."""

    tray_kinds: tuple[str, ...] = ("rect",)
    tray_keys: set[str] = TRAY_KEYS

    def __init__(self, data: dict[str, Any], source: Path | None = None):
        where = source.name if source else "template"
        _unknown(data, TOP_KEYS, where)
        self.source = source
        self.data = data
        self.name = str(data.get("name") or (source.stem if source else ""))
        if not self.name:
            raise _err(where, "a template needs a name")
        self.where = where
        self.title = str(data.get("title", self.name))
        self.description = str(data.get("description", ""))
        self.orientation = data.get("orientation", "portrait")
        if self.orientation not in ("portrait", "landscape"):
            raise _err(where, f"orientation must be portrait or landscape, not {self.orientation!r}")
        self.default_name = self.name
        self.default_title = self.title
        self.params = Schema(tuple(self._param(n, t) for n, t in data.get("params", {}).items()))
        self.lets = data.get("let", {})
        if not isinstance(self.lets, dict):
            raise _err(where, "let: expected a table of names = expressions")
        for n in self.lets:
            if n in self.params.names() or n in COMMON_NAMES or n in BUILTIN_NAMES:
                raise _err(f"{where}: let.{n}", f"{n!r} is already a parameter or a built-in name; pick another")
        intro = data.get("intro")
        if intro is not None:
            _unknown(intro, {"title", "steps", "layer", "thing", "handwriting", "example", "name_tags"},
                     f"{where}: intro")
            tags = any(isinstance(t, dict) and t.get("name_tag") for t in data.get("tokens", {}).values())
            self.intro = IntroSpec(str(intro.get("title", self.title)), tuple(intro.get("steps", ())),
                                   intro.get("layer", self._first_layer()), intro.get("thing", "token"),
                                   intro.get("handwriting", data.get("handwriting", "")),
                                   bool(intro.get("example", True)), bool(intro.get("name_tags", tags)))
        self._check_structure()

    # ------------------------------------------------------------------ declaration checks

    def _param(self, name: str, table: dict) -> Param:
        where = f"{self.where}: params.{name}"
        if name in COMMON_NAMES:
            raise _err(where, f"{name!r} is a common parameter every template has; pick another name")
        if not isinstance(table, dict):
            raise _err(where, "expected a table (type, default, help, ...)")
        _unknown(table, PARAM_KEYS, where)
        kind = table.get("type", "str")
        if kind not in TYPES:
            raise _err(where, f"unknown type {kind!r}; choose from {', '.join(TYPES)}")
        choices = table.get("choices")
        param = Param(name, kind, table.get("default"), table.get("help", ""),
                      tuple(choices) if choices is not None else None, table.get("min"), table.get("max"),
                      table.get("item", "str"), metavar=table.get("metavar"))
        if param.default is not None:
            param.coerce(param.default, f"{where}: default")
        return param

    def _first_layer(self) -> str:
        layers = self.data.get("layers") or []
        if layers:
            return layers[-1].get("name", "")
        return "Tokens" if self.data.get("trays") else ""

    def _check_structure(self):
        w = self.where
        for i, el in enumerate(self.data.get("background", []), 1):
            if el.get("type") not in ELEMENTS:
                raise _err(f"{w}: background {i}", f"type must be one of {', '.join(ELEMENTS)}, not {el.get('type')!r}")
        tokens = self.data.get("tokens", {})
        for name, tok in tokens.items():
            _unknown(tok, TOKEN_KEYS, f"{w}: tokens.{name}")
            if isinstance(tok.get("name_tag"), dict):
                _unknown(tok["name_tag"], TAG_KEYS, f"{w}: tokens.{name}.name_tag")
        names = set()
        for i, tray in enumerate(self.data.get("trays", []), 1):
            where = f"{w}: trays[{i}]"
            _unknown(tray, self.tray_keys, where)
            if tray.get("token") not in tokens:
                raise _err(where, f"token {tray.get('token')!r} is not defined (tokens: {', '.join(tokens) or 'none'})")
            if tray.get("kind", "rect") not in self.tray_kinds:
                raise _err(where, f"kind must be {' or '.join(self.tray_kinds)}, not {tray.get('kind')!r}")
            names.add(tray.get("name", f"tray{i}"))
        for i, layer in enumerate(self.data.get("layers", []), 1):
            _unknown(layer, {"name", "trays"}, f"{w}: layers[{i}]")
            if not layer.get("name"):
                raise _err(f"{w}: layers[{i}]", "a layer needs a name")
            for t in layer.get("trays", []):
                if t not in names:
                    raise _err(f"{w}: layers[{i}]", f"no tray named {t!r} (trays: {', '.join(sorted(names)) or 'none'})")

    # ------------------------------------------------------------------ Template

    def landscape(self, values: dict[str, Any]) -> bool:
        return self.orientation == "landscape"

    def intro_spec(self, values: dict[str, Any]):
        """The [intro] table, its demo token the first token on its layer, as the page draws it."""
        tray = self._intro_tray()
        if self.intro is None or tray is None:
            return self.intro

        def make(device, size_mm: float):
            names = self._names(values, device, self.title)
            where = f"{self.where}: token {tray['token']}"
            labels = self._labels(tray, names, where)
            names.update(i=0, n=1, item=labels[0] if labels else "")
            return token_maker(self._token(tray["token"], names, where))(device, size_mm)
        return replace(self.intro, token=make)

    def _names(self, values: dict[str, Any], device, document: str) -> dict[str, Any]:
        """What expressions can use: the parameters, W and H and the safe area (mm), the document name
        and the [let] names, worked out in order."""
        landscape = self.landscape(values)
        w_px, h_px = page_size(device, landscape)
        mm1 = device.mm(1)
        safe = self.style_for(values.get("theme", "default"), device).safe_area(landscape)
        names = {k: v for k, v in values.items() if k not in COMMON_NAMES}
        names.update(W=w_px / mm1, H=h_px / mm1, safe_x=safe.x / mm1, safe_y=safe.y / mm1, safe_w=safe.w / mm1,
                     safe_h=safe.h / mm1, document=document)
        for n, expr in self.lets.items():
            try:
                names[n] = number(expr, names, f"{self.where}: let.{n}")
            except ExprError as e:
                raise SchemaError(str(e)) from None
        return names

    def _local_file(self, name: str, where: str) -> str:
        """A file the template uses (an SVG), relative to the template file and inside its folder: a
        template file someone shares can't read other files on your computer."""
        if self.source is None:
            return name
        folder = self.source.parent.resolve()
        path = (folder / name).resolve()
        if Path(name).is_absolute() or not path.is_relative_to(folder):
            raise _err(where, f"{name!r} must be a file in the template's own folder ({folder.name}/), "
                              "given relative to it")
        return str(path)

    def _intro_tray(self) -> dict | None:
        """The first tray on the intro's layer (any tray, if the template names no layers)."""
        trays = self.data.get("trays", [])
        named = {t.get("name", f"tray{i}"): t for i, t in enumerate(trays, 1)}
        for layer in self.data.get("layers", []):
            if layer["name"] == self.intro.layer and layer.get("trays"):
                return named[layer["trays"][0]]
        return trays[0] if trays and not self.data.get("layers") else None

    def pages(self, values: dict[str, Any], ctx: Context) -> list[Page]:
        dev = ctx.device
        landscape = self.landscape(values)
        names = self._names(values, dev, ctx.name or self.title)
        ops = _Ops()
        for i, el in enumerate(self.data.get("background", []), 1):
            for local in self._repeat(el, names, f"{self.where}: background {i}"):
                self._element(el, local, ops, dev.mm, f"{self.where}: background {i} ({el['type']})",
                              ctx.style)
        layers: dict[str, list] = {}
        tray_strokes: dict[str, list] = {}
        trays: dict[str, TrayLayout] = {}
        for i, tray_def in enumerate(self.data.get("trays", []), 1):
            where = f"{self.where}: trays[{i}]"
            if (cond := tray_def.get("when")) and not names.get(cond):
                tray_strokes[tray_def.get("name", f"tray{i}")] = []
                continue
            tray = self._tray(tray_def, names, dev, where)
            tray_strokes[tray.name] = tray.strokes()
            trays[tray.name] = tray
            ops.areas.append((f"tray {tray.name}", tray.area))
            ops.calls.append(self._tray_call(tray, tray_def, ctx.style))
            ops.fonts.add(ctx.style.font("caption"))
        placements = []
        for layer in self.data.get("layers", []) or ([{"name": "Tokens", "trays": list(tray_strokes)}]
                                                     if tray_strokes else []):
            layers[layer["name"]] = [s for t in layer.get("trays", []) for s in tray_strokes.get(t, [])]
            placements += [pl for t in layer.get("trays", []) if t in trays
                           for pl in trays[t].placements(layer["name"])]
        ops.fonts |= {ctx.style.font(r) for r in ("title", "italic", "body")}
        hw = self.data.get("handwriting")
        if not layers and not hw:
            hw = "Writing"
        return [Page(draw=ops, layers=[Layer(n, s) for n, s in layers.items()], handwriting=hw or None,
                     handwriting_on_top=bool(self.data.get("handwriting_on_top", False)),
                     active=self.data.get("active"), landscape=landscape, fonts=tuple(sorted(ops.fonts)),
                     kind=self.name, meta={"areas": list(ops.areas), "placements": placements})]

    # ------------------------------------------------------------------ pieces

    def _repeat(self, el: dict, names: dict, where: str):
        if (cond := el.get("when")) is not None:
            if cond not in names:
                raise _err(where, f"when: unknown parameter {cond!r}")
            if not names[cond]:
                return
        rep = el.get("repeat")
        if rep is None:
            yield names
            return
        items = names.get(rep) if isinstance(rep, str) and isinstance(names.get(rep), list) else None
        try:
            count = len(items) if items is not None else int(number(rep, names, f"{where}: repeat"))
        except ExprError as e:
            raise SchemaError(str(e)) from None
        for i in range(count):
            yield {**names, "i": i, "n": i + 1, "item": items[i] if items is not None else i + 1}

    def _element(self, el: dict, names: dict, ops: _Ops, mm, where: str, style: Style):
        def num(key, default=None):
            if key not in el:
                if default is None:
                    raise _err(where, f"missing {key!r}")
                return default
            try:
                return number(el[key], names, f"{where}: {key}")
            except ExprError as e:
                raise SchemaError(str(e)) from None

        def text(key, default=""):
            try:
                return fill(el.get(key, default), names, f"{where}: {key}")
            except ExprError as e:
                raise SchemaError(str(e)) from None

        def colour(key, default=None):
            token = el.get(key, default)
            if token is None:
                return None
            try:
                return style.color(str(token))
            except ValueError as e:
                raise _err(where, f"{key}: {e}") from None

        kind = el["type"]
        color = colour("color", "ink")
        width = mm(num("width", 0.3))
        line_style = el.get("style", "solid")
        fill_color = colour("fill")
        if kind in ("text", "passage"):
            s, role = str(text("text")), el.get("font", "title" if kind == "text" else "body")
            tracking = 0.0
            if role in ROLES:
                t = style.type(role)
                font_name, tracking = t.font, t.tracking
                s = s.upper() if t.caps else s
                color = colour("color", t.color)
            else:
                font_name = role
            try:
                fonts.font(font_name)
            except ValueError as e:
                raise _err(where, f"font: {e} (or use a text role: {', '.join(ROLES)})") from None
            ops.fonts.add(font_name)
            if kind == "passage":
                ops.areas.append(("passage", Rect(mm(num("x")), mm(num("y")), mm(num("w")), mm(num("h")))))
                ops.calls.append(_passage(s, el, num, mm, font_name, tracking, color,
                                          colour("line_color", "ink"), width if "width" in el else mm(style.lines.rule),
                                          where))
                return
            x, y, size = mm(num("x")), mm(num("y")), mm(num("size", 4))
            align, rotate = el.get("align", "left"), num("rotate", 0)
            if "max_w" in el:
                tw = fonts.text_width(s, font_name, size) + tracking * size * max(len(s) - 1, 0)
                size = min(size, size * mm(num("max_w")) / tw) if tw else size
            if not rotate:
                tw = fonts.text_width(s, font_name, size) + tracking * size * max(len(s) - 1, 0)
                x0 = x - (tw / 2 if align == "center" else tw if align == "right" else 0)
                ops.areas.append(("text", Rect(x0, y - size * 0.75, tw, size)))
            ops.calls.append(lambda p: p.text(s, x, y, font_name, size, color, align, rotate,
                                              char_space=tracking * size))
        elif kind == "line":
            pts = (mm(num("x1")), mm(num("y1")), mm(num("x2")), mm(num("y2")))
            ops.calls.append(_styled(line_style, width, color, lambda p: p.line(*pts, width, color)))
        elif kind == "rect":
            r = Rect(mm(num("x")), mm(num("y")), mm(num("w")), mm(num("h")))
            ops.areas.append(("rect", r))
            radius = mm(num("radius", 0))
            stroke = None if el.get("stroke") is False else color
            ops.calls.append(_styled(line_style, width, color, lambda p: p.rect(
                r, fill=fill_color, stroke=stroke, width=width, radius=radius)))
        elif kind == "circle":
            cx, cy, rad = mm(num("cx")), mm(num("cy")), mm(num("r"))
            stroke = None if el.get("stroke") is False else color
            ops.calls.append(_styled(line_style, width, color, lambda p: p.circle(
                cx, cy, rad, fill=fill_color, stroke=stroke, width=width)))
        elif kind == "sectors":
            self._sectors(el, names, ops, mm, num, text, color, width, where, style)
        elif kind == "write-in":
            field_ = WriteIn(str(text("label")), str(text("after")), el.get("kind", "line"), str(text("value")))
            r = Rect(mm(num("x")), mm(num("y")), mm(num("w")), mm(num("h", 9)))
            ops.areas.append(("write-in", r))
            fstyle = FieldStyle.from_style(style, num("size") if "size" in el else None)
            ops.fonts |= {fstyle.label_font, fstyle.text_font}
            ops.calls.append(lambda p: draw_write_in(p, field_, r, fstyle))
        elif kind == "lines":
            r = Rect(mm(num("x")), mm(num("y")), mm(num("w")), mm(num("h")))
            pitch = mm(num("pitch", 8))
            ops.areas.append(("lines", r))
            if pitch <= 0:
                raise _err(where, "pitch must be positive")
            line_color = colour("color", "rule")

            def ruled(p, r=r, pitch=pitch):
                y = r.y + pitch
                while y <= r.bottom + 1e-6:
                    p.line(r.x, y, r.right, y, width, line_color)
                    y += pitch
            ops.calls.append(ruled)

    def _sectors(self, el, names, ops, mm, num, text, color, width, where, style: Style):
        """A radial chart: `count` sectors between radius `inner` and `r`, spokes and rims, optional
        dotted `levels` rings and a label per sector outside the rim."""
        cx, cy, r = mm(num("cx")), mm(num("cy")), mm(num("r"))
        inner, count = mm(num("inner", 0)), int(num("count"))
        start, levels = num("start", -90), int(num("levels", 0))
        if count < 1 or r <= inner:
            raise _err(where, "needs count >= 1 and r > inner")
        labels = text("labels", []) if "labels" in el else []
        if isinstance(labels, str):
            labels = [s.strip() for s in labels.split(",")]
        label_size = mm(num("label_size", 3.4))
        label_r = mm(num("label_r", 0)) or r + label_size * 1.6
        shade = bool(el.get("shade", False))
        shade_color, ring_color = style.color("surface"), style.color("rule")
        label_font = style.font("label")
        ops.fonts.add(label_font)

        def draw(p: Painter):
            c = p.c
            step = 360 / count
            if shade:
                for k in range(0, count, 2):
                    a0 = start + k * step
                    pts = [(cx + r * math.cos(math.radians(a)), cy + r * math.sin(math.radians(a)))
                           for a in (a0 + step * j / 24 for j in range(25))]
                    inner_pts = [(cx + inner * math.cos(math.radians(a)), cy + inner * math.sin(math.radians(a)))
                                 for a in (a0 + step - step * j / 24 for j in range(25))]
                    p.polyline(pts + inner_pts, 0.01, shade_color, closed=True, fill=shade_color)
            for lv in range(1, levels + 1):
                rr = inner + (r - inner) * lv / (levels + 1)
                c.saveState()
                p.dash("dotted", width, mm(1.2))
                p.circle(cx, cy, rr, stroke=ring_color, width=width)
                c.restoreState()
            p.circle(cx, cy, r, stroke=color, width=width)
            if inner > 0:
                p.circle(cx, cy, inner, stroke=color, width=width)
            for k in range(count):
                a = math.radians(start + k * step)
                p.line(cx + inner * math.cos(a), cy + inner * math.sin(a), cx + r * math.cos(a),
                       cy + r * math.sin(a), width, color)
            for k, label in enumerate(labels[:count]):
                a = math.radians(start + (k + 0.5) * step)
                p.label(str(label), cx + label_r * math.cos(a), cy + label_r * math.sin(a), label_font,
                        label_size, color)
        ops.calls.append(draw)

    def _token(self, name: str, names: dict, where: str) -> Token:
        d = self.data["tokens"][name]

        def num(key, default):
            if key not in d:
                return default
            try:
                return number(d[key], names, f"{where}: {key}")
            except ExprError as e:
                raise SchemaError(str(e)) from None
        tag = d.get("name_tag")
        name_tag = None
        if tag:
            tag = tag if isinstance(tag, dict) else {}
            try:
                size = [number(tag.get(k, d), names, f"{where}: name_tag.{k}")
                        for k, d in (("width", 20), ("height", 7), ("overlap", 0.8))]
                name_tag = NameTag(size[0], size[1], tag.get("side", "below"), tag.get("style", "box"), size[2],
                                   bool(tag.get("knockout", False)))
            except ValueError as e:
                raise _err(where, str(e)) from None
        shape = d.get("shape", "circle")
        if shape.endswith(".svg"):
            shape = self._local_file(shape, f"{where}: shape")
        icon = d.get("icon")
        if icon:
            icon = self._local_file(icon, f"{where}: icon")
        label = fill(d.get("label", ""), names, f"{where}: label")
        number_ = int(num("number", 0)) if "number" in d else None
        try:
            tok = Token(shape, num("size", 10.0), num("height", None), d.get("style", "outline"), num("pen", 0.3),
                        str(label), number_, icon, name_tag, d.get("svg_units"))
            tok.check()
        except ValueError as e:
            raise _err(where, str(e)) from None
        return tok

    def _labels(self, t: dict, names: dict, where: str) -> list:
        labels = fill(t.get("labels", []), names, f"{where}: labels") if "labels" in t else []
        return [s.strip() for s in labels.split(",")] if isinstance(labels, str) else list(labels)

    def _tray(self, t: dict, names: dict, dev, where: str) -> TrayLayout:
        mm = dev.mm

        def num(key, default=None):
            if key not in t:
                if default is None:
                    raise _err(where, f"missing {key!r}")
                return default
            try:
                return number(t[key], names, f"{where}: {key}")
            except ExprError as e:
                raise SchemaError(str(e)) from None
        count = int(num("count", 1))
        labels = self._labels(t, names, where)
        arts, toks = [], []
        for i in range(count):
            local = {**names, "i": i, "n": i + 1, "item": labels[i] if i < len(labels) else ""}
            toks.append(self._token(t["token"], local, f"{where}: token {t['token']}"))
            arts.append(token_art(toks[-1], dev))
        pad = mm(num("pad", SLOT_PAD_MM))
        sw = max((a.width for a in arts), default=0) + pad
        sh = max((a.height for a in arts), default=0) + pad
        label = str(fill(t.get("label", ""), names, f"{where}: label"))
        try:
            area, cells = self._tray_cells(t, num, mm, count, sw, sh)
        except ValueError as e:
            mm1 = mm(1)
            if "don't fit" in str(e) or "overlap" in str(e):
                raise _err(where, f"{count} {t['token']} tokens ({sw / mm1:.0f} x {sh / mm1:.0f} mm each, "
                                  f"with padding) don't fit; make the tray bigger, the tokens or their "
                                  "name tags smaller, or ask for fewer") from None
            raise _err(where, str(e)) from None
        return TrayLayout(t.get("name", "tray"), area, tuple(cells), tuple(arts), label, tuple(toks))

    def _tray_cells(self, t: dict, num, mm, count: int, slot_w: float, slot_h: float):
        """(area, [(box, rotation), ...]) in page px: `count` slots in rows across x, y, w, h."""
        area = Rect(mm(num("x")), mm(num("y")), mm(num("w")), mm(num("h")))
        cols = int(num("columns")) if t.get("columns") is not None else None
        return area, [(r, 0.0) for r in grid_cells(area, count, slot_w, slot_h, mm(num("gap", 1.5)), cols)]

    def _tray_call(self, tray: TrayLayout, t: dict, style: Style):
        """What the tray prints on the background: a frame round its area (`frame = true`) and its
        label above it, in the caption style."""
        frame = bool(t.get("frame", False))
        caption = style.type("caption")

        def draw(p: Painter):
            if frame:
                p.rect(tray.area, stroke=style.color("guide"), width=p.mm(style.lines.dot), radius=p.mm(2))
            if tray.label:
                size = p.mm(caption.size_mm)
                p.text(tray.label.upper() if caption.caps else tray.label, tray.area.x, tray.area.y - p.mm(1.5),
                       caption.font, size, style.color(caption.color), char_space=caption.tracking * size)
        return draw


def _styled(style: str, width: float, color: str, call):
    if style == "solid":
        return call

    def draw(p: Painter):
        p.c.saveState()
        p.c.setStrokeColor(HexColor(color))
        p.dash(style, width, p.mm(1.0), p.mm(2.0))
        call(p)
        p.c.restoreState()
    return draw


def _passage(text: str, el: dict, num, mm, font_name: str, tracking: float, color: str, line_color: str,
             line_width: float, where: str):
    """Text wrapped into x, y, w, h: `\n` starts a new line, and every run of three or more
    underscores is a gap, a line `blank` mm long to write on or to drop a token onto. Lines are
    `leading` mm apart (room for a token on a gap); the text shrinks, down to `min_size`, until
    it fits."""
    x, y, w, h = mm(num("x")), mm(num("y")), mm(num("w")), mm(num("h"))
    size_mm = num("size", 4.2)
    size, min_size = mm(size_mm), mm(num("min_size", size_mm * 0.75))
    leading = mm(num("leading", size_mm * 1.9))
    blank = min(mm(num("blank", 25)), w)
    if leading <= 0 or w <= 0:
        raise _err(where, "leading and w must be positive")

    def width(piece: str, s: float) -> float:
        if GAP.fullmatch(piece):
            return blank
        return fonts.text_width(piece, font_name, s) + tracking * s * max(len(piece) - 1, 0)

    def wrap(s: float) -> list[list[list[str]]]:
        """Lines of words, each word its pieces (text and gaps)."""
        space = fonts.text_width(" ", font_name, s)
        lines = []
        for paragraph in text.split("\n"):
            line, used = [], 0.0
            for word in paragraph.split():
                pieces = [p for p in GAP.split(word) if p]
                ww = sum(width(p, s) for p in pieces)
                if line and used + space + ww > w + 1e-6:
                    lines.append(line)
                    line, used = [], 0.0
                used += (space if line else 0) + ww
                line.append(pieces)
            lines.append(line)
        return lines

    while True:
        lines = wrap(size)
        if len(lines) * leading <= h + 1e-6:
            break
        if size - mm(0.25) < min_size - 1e-6:
            raise _err(where, f"the text needs {len(lines)} lines ({len(lines) * leading / mm(1):.0f} mm) but the "
                              f"area is {h / mm(1):.0f} mm high; shorten it, make the area taller or the "
                              "leading smaller")
        size -= mm(0.25)

    def draw(p: Painter):
        for k, line in enumerate(lines):
            base = y + (k + 0.75) * leading
            # The text between two gaps is set as one run, so it reads as text in the PDF.
            run, start = "", x
            for j, pieces in enumerate(line):
                for m, piece in enumerate(pieces):
                    if GAP.fullmatch(piece):
                        gap_x = start + width(run, size)
                        p.text(run, start, base, font_name, size, color, char_space=tracking * size)
                        p.line(gap_x, base + mm(1), gap_x + blank, base + mm(1), line_width, line_color)
                        run, start = "", gap_x + blank
                    else:
                        run += piece
                    if m == len(pieces) - 1 and j < len(line) - 1:
                        run += " "
            p.text(run, start, base, font_name, size, color, char_space=tracking * size)
    return draw
