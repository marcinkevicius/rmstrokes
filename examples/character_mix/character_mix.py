"""Character mix & match: an rmstrokes example (a Python template file).

    rmstrokes make examples/character_mix/character_mix.py -o out/character-mix.rmdoc
    rmstrokes make examples/character_mix/character_mix.py --cards 2 --device pro -o out/
    rmstrokes make examples/character_mix/character_mix.py --help        # every parameter

Build people from parts. The background PDF has the title, a row of blank cards with a line for a
name, and a caption over each group of parts. Every part is movable pen strokes, one compact
cluster each, on a layer of its own kind, bottom to top: bodies, heads, faces, facial hair,
accessories. So a head covers the neck of the body it is dropped on, and a face sits on the head:
bodies and heads are drawn over opaque white ink. Select a part's layer, lasso the part and drag it
onto a card; write the name on the handwriting layer.

The parts are a few pieces of Open Peeps by Pablo Stanley (https://www.openpeeps.com/, CC0 1.0), cut
apart and listed in parts/LICENSE.md and the package's ATTRIBUTION.md. Each part keeps its place in
the original 240 x 324 bust, so all parts are drawn at one scale and fit each other. The scale is
the largest at which the cards and every part fit the page.

Only the reMarkable 2 has been checked on hardware; the Paper Pro and Move output is unverified.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from rmstrokes import (
    Context,
    FieldStyle,
    FitError,
    IntroSpec,
    Layer,
    Page,
    Param,
    Placement,
    Rect,
    Schema,
    Template,
    Token,
    WriteIn,
    draw_write_in,
    grid_cells,
    token_art,
    token_maker,
)

PARTS_DIR = Path(__file__).resolve().parent / "parts"
# Kind -> (layer, file name prefixes, SVG style), bottom layer first.
KINDS = {
    "bodies": ("Bodies", ("body-",), "white-fill"),
    "heads": ("Heads", ("head-",), "white-fill"),
    "faces": ("Faces", ("face-",), "filled"),
    "facial-hair": ("Facial hair", ("beard-",), "filled"),
    "accessories": ("Accessories", ("glasses", "sunglasses", "eyepatch"), "filled"),
}
# The parts are shown in these groups, a caption over each (the small parts share one).
SECTIONS = (("bodies",), ("heads",), ("faces", "facial-hair", "accessories"))
HANDWRITING = "Handwriting"
# The bust the parts were cut from, in its own units: where a whole person sits on a card.
PERSON = (31.0, 24.0, 203.5, 290.6)   # x0, y0, x1, y1
SCALES = [s / 1000 for s in range(260, 79, -2)]  # mm per bust unit, largest first
CREDIT = "Characters: Open Peeps by Pablo Stanley (CC0)"


def _check_parts(kinds: list[str]) -> None:
    if bad := [k for k in kinds if k not in KINDS]:
        raise ValueError(f"unknown part kind(s) {', '.join(bad)}; choose from {', '.join(KINDS)}")
    if not kinds:
        raise ValueError("give at least one part kind")


PARAMS = Schema((
    Param("title", "str", "Mix & match", "heading printed at the top"),
    Param("cards", "int", 3, "blank cards to build a person on", min=1, max=4, metavar="N"),
    Param("card_label", "str", "Who is this?", "the label of each card's name line"),
    Param("parts", "list", list(KINDS), f"part kinds to include, comma separated ({', '.join(KINDS)})",
          cli="csv", metavar="A,B,...", check=_check_parts),
))


# --------------------------------------------------------------------------- the parts

@dataclass(frozen=True)
class Part:
    kind: str
    path: Path
    x: float  # its box in bust units (the SVG's viewBox)
    y: float
    w: float
    h: float

    def token(self, k: float) -> Token:
        return Token(str(self.path), size_mm=round(self.w * k, 3), style=KINDS[self.kind][2], svg_units=self.w)


def chosen(values: dict[str, Any]) -> list[str]:
    """The kinds to show, bottom layer first, whatever order they were given in."""
    return [kind for kind in KINDS if kind in values["parts"]]


def parts(kind: str) -> list[Part]:
    found = []
    for path in sorted(PARTS_DIR.glob("*.svg")):
        if path.name.startswith(KINDS[kind][1]):
            m = re.search(r'viewBox="([-\d. ]+)"', path.read_text())
            found.append(Part(kind, path, *map(float, m[1].split())))
    return found


# --------------------------------------------------------------------------- layout

@dataclass
class Layout:
    k: float                                         # mm per bust unit
    title_y: float
    hint_y: float
    cards: list[Rect]
    captions: list[tuple[str, float, float]]         # (text, x, baseline)
    placed: dict[str, list[tuple[Part, Rect]]]       # kind -> parts and their boxes, page px
    credit_y: float


def _shelves(items: list[tuple[Part, float, float]], x0: float, width: float, y: float, gap: float):
    """Left-to-right rows of (part, w, h) boxes, wrapping at `width`, each row centred; returns the
    boxes and the y below the last row."""
    rows, row, used = [], [], 0.0
    for item in items:
        if row and used + gap + item[1] > width:
            rows.append(row)
            row, used = [], 0.0
        used += (gap if row else 0) + item[1]
        row.append(item)
    if row:
        rows.append(row)
    boxes = []
    for row in rows:
        h = max(i[2] for i in row)
        x = x0 + (width - sum(i[1] for i in row) - gap * (len(row) - 1)) / 2
        for part, w, ph in row:
            boxes.append((part, Rect(x, y + (h - ph) / 2, w, ph)))
            x += w + gap
        y += h + gap
    return boxes, y - gap


def layout(ctx: Context, values: dict[str, Any]) -> Layout:
    style, device = ctx.style, ctx.device
    mm = device.mm
    safe, gutter = style.safe_area(), mm(style.spacing.gutter)  # clear of the toolbar on the left
    left, width = safe.x, safe.w
    title_y = safe.y + style.size("title")
    hint_y = title_y + mm(2) + style.size("italic")
    top = hint_y + mm(6)
    credit_y = safe.bottom - style.size("small") * 0.25  # descenders stay above the margin
    bottom = credit_y - style.size("small") - mm(3)
    caption_h = style.size("caps") + mm(2)
    kinds = chosen(values)
    for k in SCALES:
        px = mm(k)
        person_w, person_h = (PERSON[2] - PERSON[0]) * px, (PERSON[3] - PERSON[1]) * px
        card_w, card_h = person_w + mm(6), person_h + mm(14)
        try:
            cards = grid_cells(Rect(left, top, width, card_h), values["cards"], card_w, card_h,
                               gutter, columns=values["cards"])
        except FitError:
            continue
        y = top + card_h + mm(8)
        captions, placed = [], {}
        for section in SECTIONS:
            shown = [kind for kind in section if kind in kinds]
            if not shown:
                continue
            captions.append((", ".join(KINDS[kind][0] for kind in shown), left,
                             y + style.size("caps")))
            y += caption_h
            items = [(p, p.w * px, p.h * px) for kind in shown for p in parts(kind)]
            boxes, y = _shelves(items, left, width, y, mm(3))
            for kind in shown:
                placed[kind] = [(part, box) for part, box in boxes if part.kind == kind]
            y += mm(4)
        if y - mm(4) <= bottom:
            return Layout(k, title_y, hint_y, cards, captions, placed, credit_y)
    raise FitError(f"{values['cards']} cards and the parts don't fit on the {device.name} page")


# --------------------------------------------------------------------------- the template

class CharacterMix(Template):
    name = "character-mix"
    title = "Character mix & match"
    description = ("Build people from parts: bodies, heads, faces, facial hair and accessories as movable "
                   "pen strokes, a layer per kind, and blank cards with a name line (Open Peeps, CC0)")
    params = PARAMS
    default_name = "character-mix"
    default_title = "Mix & match"
    seed_namespace = "rmstrokes-character-mix"

    def intro_spec(self, values: dict[str, Any]) -> IntroSpec:
        kinds = chosen(values)
        demo = "heads" if "heads" in kinds else kinds[-1]  # a head reads best as the practice part
        return IntroSpec("Mix & match", (
            "Pick the layer of the part you want to move.",
            "Lasso the part and drag it onto a card.",
            f"Stack them up: {', '.join(KINDS[k][0].lower() for k in kinds)}.",
            f"Write each name on “{HANDWRITING}”.",
        ), layer=KINDS[demo][0], thing="part", handwriting=HANDWRITING, name_tags=False,
            token=token_maker(parts(demo)[0].token(0.2)))

    def pages(self, values: dict[str, Any], ctx: Context) -> list[Page]:
        style, device = ctx.style, ctx.device
        lay = layout(ctx, values)
        layers, placements = [], []
        for kind in chosen(values):
            name = KINDS[kind][0]
            placed = [Placement(name, token, token_art(token, device), box)
                      for part, box in lay.placed[kind] for token in [part.token(lay.k)]]
            layers.append(Layer(name, [s for pl in placed for s in pl.strokes()]))
            placements += placed
        field_style = FieldStyle.from_style(style)
        tints = [f"accent-{i}-tint" for i in range(1, 5)] if style.color_ok else ["surface-faint"] * 4

        def draw(p):
            mm = device.mm
            safe = style.safe_area()
            style.draw_text(p, values["title"], safe.x, lay.title_y, "title")
            style.draw_text(p, "Pick a layer, lasso a part, drag it onto a card.", safe.x, lay.hint_y, "italic")
            for i, card in enumerate(lay.cards):
                p.rect(card, fill=style.color(tints[i]), stroke=style.color("rule"), width=style.line("rule"),
                       radius=mm(2))
                # The label above the line, so a narrow card still leaves room to write.
                style.draw_text(p, values["card_label"], card.x + mm(3), card.bottom - mm(9), "field")
                draw_write_in(p, WriteIn(), Rect(card.x + mm(3), card.bottom - mm(8), card.w - mm(6), mm(7)),
                              field_style)
            for text, x, y in lay.captions:
                style.draw_text(p, text, x, y, "caps")
            style.draw_text(p, CREDIT, safe.right, lay.credit_y, "small", align="right")

        return [Page(draw=draw, layers=layers, handwriting=HANDWRITING, handwriting_on_top=True,
                     active=layers[-1].name, fonts=style.fonts, kind=self.name,
                     meta={"layout": lay, "placements": placements, "areas": [("card", c) for c in lay.cards]})]

    def summary(self, result, doc, values: dict[str, Any], ctx: Context) -> str:
        n = sum(len(parts(k)) for k in chosen(values))
        return (f"{result.path}: {ctx.device.name}, {values['cards']} card(s), {n} parts, "
                f"{len(doc.pages)} page(s), {result.size_kib():.1f} KiB")


TEMPLATE = CharacterMix()
