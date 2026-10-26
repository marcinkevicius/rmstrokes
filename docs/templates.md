# Template files

A template turns parameter values into pages. Templates written as data are TOML files: what's printed on the
background, what tokens there are, which tray they start in, on which layer. The built-in `gaps`
(`src/rmstrokes/builtin/gaps.toml`) and [examples/templates/sorting.toml](../examples/templates/sorting.toml) are
complete examples.

```bash
rmstrokes make my-template.toml --help        # its parameters as flags
rmstrokes make my-template.toml -o out.pdf    # the PDF prints the strokes too: quick to check by eye
```

In a recipe, `template = "my-template.toml"` is relative to the recipe file.

## Top level

| Key | | |
|---|---|---|
| `name` | text | the template's name (default: the file name) |
| `title`, `description` | text | shown by `rmstrokes templates` and on the intro page |
| `orientation` | `portrait` \| `landscape` | default portrait |
| `handwriting` | text | name of an empty layer added under the stroke layers, to write on (default `Writing` if there are no stroke layers) |
| `handwriting_on_top` | bool | put that layer above the stroke layers instead |
| `active` | text | the layer selected when the page opens (default: the top stroke layer) |
| `[params.<name>]` | table | a parameter, see below |
| `[let]` | table | named numbers worked out from the others, see below |
| `[intro]` | table | this template's part of the intro page |
| `[[background]]` | tables | what's printed, in order |
| `[tokens.<name>]` | table | what a kind of token looks like |
| `[[trays]]` | tables | where tokens start |
| `[[layers]]` | tables | stroke layers, bottom to top, and which trays' tokens they hold |

## Parameters

```toml
[params.tokens]
type = "int"          # str, int, float, bool, choice, list, path
default = 6
min = 1               # int/float (and each item of a list)
max = 12
help = "how many tokens"
# choices = ["a", "b"]   for type = "choice"
# item = "int"           list item type (str, int, float)
```

Every template also has the common parameters `device`, `theme`, `name`, `copies` and `intro`; a template can't
declare those names. CLI flags are the names with dashes (`--words-per-page`); a bool is `--x` / `--no-x`, a list is a
repeatable flag. Values are checked before anything is drawn, and errors say which parameter is wrong and why:
`gaps: copies: must be at least 1 (got 0)`.

## Numbers and text

Lengths are **millimetres**, from the top-left corner of the page. Any number may be an expression over:

- `W`, `H`: the page size in mm (it differs per device: rM2 157.8 × 210.4, Paper Pro 179.7 × 239.6, Move 91.8 × 163.2);
- `safe_x`, `safe_y`, `safe_w`, `safe_h`: the safe area in mm, where content goes on this device: inside the
  design system's margin, and clear of the 14 mm strip at the left edge that the open toolbar covers
  (`Style.safe_area()`; rM2 `14, 8, 135.8, 194.4`). The built-in template and the examples keep everything inside it,
  and a test checks that on every device;
- the template's parameters (`tokens`, `len(groups)`);
- in a `repeat`, `i` (0, 1, ...), `n` (1, 2, ...) and `item` (the list entry);

with `+ - * / // % **`, parentheses and `min max abs round floor ceil sqrt sin cos len longest` (angles in degrees;
`longest(words)` is the length of the longest item of a list): `x = "14 + i * (W - 28) / tokens"`. Nothing else is allowed (no attributes, imports or calls of other
functions). Text may contain `{param}`; a value that is exactly `"{param}"` keeps its type (a list stays a list).
`{{` and `}}` are literal braces.

**`[let]`** names a number once and uses it everywhere: each entry is an expression over `W`, `H`, the parameters and
the entries above it, worked out once per page (and for the intro page's token).

```toml
[let]
tag_w = "min(W - 32, 10 + 2.4 * longest(words))"      # every word tag as wide as the longest word needs
cols = "max(1, floor((W - 28 + 1.5) / (tag_w + 3.5)))"
rows = "ceil(len(words) / cols)"
bank_y = "H - 12 - rows * 11.5"
```

A `[let]` name can't be a parameter's or one of `W H i n item document`.

Design for the narrowest device: the Paper Pro Move is 92 mm wide. `min(...)` keeps a size sensible everywhere, e.g.
`name_tag = { width = "min(19, (W - 34) / 3 - 2)" }` fits three tokens per row on the Move.

## Background elements

Every element has a `type`; `repeat = <count or list parameter>` draws it once per item, `when = "<bool parameter>"`
only when that parameter is true. Colours are palette tokens of the theme (`ink`, `muted`, `rule`, `guide`, `surface`,
`accent-1` ... `accent-6`, `accent-2-tint`, `pair-a`, ...) or `#RRGGBB`; widths in mm. The theme (`--theme default |
color`, or a theme another package registers) decides what the tokens and text roles look like: see [design-system.md](design-system.md).

| `type` | Keys |
|---|---|
| `text` | `text`, `x`, `y` (baseline), `size` (mm, default 4), `font` (a text role of the theme, default `title`, or a font file name), `align` (`left` \| `center` \| `right`), `rotate`, `color`, `max_w` (shrink to fit) |
| `passage` | text wrapped into `x`, `y`, `w`, `h`: `text` (`\n` starts a new line; three or more underscores `___` make a gap, a line to write on or drop a token onto), `size` (default 4.2), `min_size` (it shrinks to this to fit, default ¾ of `size`), `leading` (mm from line to line, default 1.9 × `size`: leave room for a token on a gap), `blank` (gap length, default 25), `font` (default `body`), `color`, `line_color` (the gaps, default `ink`), `width` (their line width) |
| `line` | `x1`, `y1`, `x2`, `y2`, `width`, `color`, `style` (`solid` \| `dotted` \| `dashed`) |
| `rect` | `x`, `y`, `w`, `h`, `radius`, `width`, `color`, `fill`, `stroke = false` (no outline), `style` |
| `circle` | `cx`, `cy`, `r`, `width`, `color`, `fill`, `stroke = false`, `style` |
| `sectors` | a radial chart: `cx`, `cy`, `r`, `inner` (default 0), `count`, `start` (degrees, default -90 = top), `levels` (dotted circles), `labels` (list), `label_r`, `label_size`, `shade` (alternate sectors grey) |
| `write-in` | `label`, `after`, `kind` (`line` \| `box` \| `lines`), `x`, `y`, `w`, `h` (default 9), `size`, `value` (pre-filled) |
| `lines` | ruled lines: `x`, `y`, `w`, `h`, `pitch` (default 8), `width`, `color` |

Text roles (`font = "..."`): `title`, `heading`, `label`, `body`, `value`, `italic`, `caps`, `caption`, `field`,
`small`, `numeric`. A role brings its font, colour (unless `color` is given), capitals and letter spacing; `size` is
still the element's own. Fonts bundled, by file name: `AtkinsonHyperlegibleNext-Regular`, `-Italic`, `-SemiBold`.
Any other font is found by the same name once a font package that ships it is installed (entry point group
`rmstrokes.fonts`) or its folder is registered with `fonts.add_font_source`.

## Tokens

```toml
[tokens.dot]
shape = "circle"        # circle square rounded diamond star heart pin tag arrow, or an .svg file in the template's folder
size = 9                # width in mm (height: the shape's own aspect, or height = ...)
style = "white-fill"    # outline | filled | grey | white-fill (an SVG: filled | white-fill | outline)
pen = 0.3               # mm
number = "n"            # an expression: 1, 2, ... per slot
# label = "{item}"      # text in the stroke font (letters, digits, - + . , ! ? ' : / # ( )); labels = [...] on the tray
# icon = "my-icon.svg"    # an SVG drawn inside the shape
name_tag = { width = 20, height = 7, side = "below", style = "box" }   # side: below | right; style: box | line
# knockout = true in name_tag fills the tag with white ink, so lines under the token don't cross the name
```

A token is drawn as one contiguous run of strokes: shape, icon and label, then the name tag, which overlaps the
shape's edge by `overlap` (default 0.8 mm) so the two touch. **Write a name in the tag with the pen on the token's
layer**, and one lasso round the token takes the token and the name together.

## Trays

A tray is where tokens start: a grid of slots, one token in each, in rows across an area.

```toml
[[trays]]
name = "start"
token = "dot"
count = "tokens"         # how many tokens start here
labels = "{names}"       # optional: one label per token (as item)
x = 14                   # the area, in mm
y = "H - 66"
w = "W - 28"
h = 56
gap = 1.5                # mm between slots (default 1.5)
columns = 4              # default: as many as fit
label = "Start here"   # printed above the tray
frame = true                     # a rounded frame round the area
pad = 2                          # mm around each token in its slot
# when = "show_tray"             # only when this bool parameter is true
```

The slots are centred in the area, a last, shorter row too. If the tokens don't fit, the error says how big they are:
`trays[1]: 10 dot tokens (20 x 15 mm each, with padding) don't fit; ...`. Another package can add tray kinds by subclassing `rmstrokes.datatemplate.DataTemplate` (`tray_kinds`, `tray_keys`, `_tray_cells`, `_tray_call`).

## Layers and the intro page

```toml
[[layers]]
name = "Tokens"
trays = ["start"]

[intro]
title = "Sorting"
thing = "token"                      # what you move, for the generic steps
steps = ["Write a name in each token's tag.", "Drag the tokens into the boxes."]
# layer = "Tokens"                   default: the top stroke layer
# example = false                    leave out the miniature of the page
# name_tags = false                  default: true if any token has a name_tag ("Name it" card, else "Take notes")
```

The intro's cards and practice token show the first token of the intro's layer, as the page draws it.

Keep the steps to three to five, one short sentence each, verb first ("Drag each word into the box where it belongs.").
The generic cards (pick the layer, lasso, drag, write, show or hide, try it) already explain the tablet's tools, so
the steps only say what is special about this template.

Without `[[layers]]`, every tray's tokens go on one layer called `Tokens`.

## Templates in Python

Subclass `rmstrokes.Template`: declare `params` (a `Schema` of `Param`s), implement `pages(values, ctx)` returning
`Page`s, and optionally `intro`/`intro_spec(values)`, `themes()`, `color_theme` (the theme for colour devices, used
by `rmstrokes gallery`), `landscape(values)`, `document_meta`, `summary`.
Publish it under the `rmstrokes.templates` entry point group so `rmstrokes build` and recipes find it by name.

Or keep it as a file: a `.py` file that defines `TEMPLATE` (an instance, or the class) works wherever a template file
does, without installing anything: `rmstrokes make path/to/my_template.py --help`, or `template = "my_template.py"`
in a recipe (relative to the recipe; `rmstrokes build --allow-python`, since the file runs as code). A recipe also finds it by name when it sits next to the recipe and is named
after the template, `_` for `-`: `template = "my-page"` loads `my_page.py` (a file whose `TEMPLATE` has
another name is refused). `rmstrokes.templates.register_file(path)` makes a file available by name everywhere in the
process; the gallery config's `templates` list does that. The file runs once, and can find its own assets (icons, say) next to its
`__file__`.
