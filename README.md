# rmstrokes

[![CI](https://github.com/marcinkevicius/rmstrokes/actions/workflows/ci.yml/badge.svg?branch=main)](https://github.com/marcinkevicius/rmstrokes/actions/workflows/ci.yml)
[![Python](https://img.shields.io/badge/python-3.11%20%7C%203.12%20%7C%203.13-blue?logo=python&logoColor=white)](https://github.com/marcinkevicius/rmstrokes/blob/main/pyproject.toml)
[![License](https://img.shields.io/badge/license-MIT-green)](https://github.com/marcinkevicius/rmstrokes/blob/main/LICENSE)

**Printable pages with movable pieces, for the reMarkable.**

![Three pages made with rmstrokes: the how-to page, a fill-in-the-gaps page with word tags, and a character mix-and-match page](https://raw.githubusercontent.com/marcinkevicius/rmstrokes/main/docs/images/pages.png)

*The how-to page, fill in the gaps, and the character mix example, as PDF. On the tablet, every word tag and character part is pen strokes you can lasso and move.*

reMarkable documents with a PDF background and **movable pen strokes**: draw the fixed part of a page as a vector PDF,
put the things people move (tokens, word tags, pictures, pins) on named layers as real pen strokes, and write it all as an
`.rmdoc` the tablet opens like any notebook. Select the layer, lasso a thing, drag it.

> [!NOTE]
> Early days. It's been tried on a **reMarkable 2**; Paper Pro and Paper Pro Move output is built from published
> specs and hasn't been tried on those tablets yet. If you have one, a quick
> [report](https://github.com/marcinkevicius/rmstrokes/blob/main/CONTRIBUTING.md#the-most-useful-thing-a-paper-pro-or-move-report) would help a lot.

## Features

- **SVG and shapes to strokes:** any SVG (or a primitive: circle, star, pin, tag, arrow, ...) becomes fineliner
  strokes: a contour along the edge, a scanline hatch inside, thin features patched; filled, grey, outline or over
  opaque white ink. Each object is one compact, contiguous cluster, so one lasso takes exactly one object.
- **Layer API:** a page is one PDF background plus any number of named stroke layers and an optional empty
  handwriting layer (`Page`, `Layer`, `Document`).
- **Tokens:** a shape with an optional icon, label or number, and an optional blank **name tag** attached on the
  same layer: write a name in the tag and one lasso moves the token and the name together.
- **Trays:** where tokens start: a grid of slots (`grid_cells`), with an optional label and frame.
- **Write-in fields:** a label and a ruled line or box on the background (`Today I will ________ first`).
- **Templates as data:** a TOML file declares the parameters, the background, the tokens and their trays
  ([docs/templates.md](https://github.com/marcinkevicius/rmstrokes/blob/main/docs/templates.md)). Built in: `gaps` (fill in the gaps: a passage with gaps and a bank of
  word tags to drag into them).
- **One parameter schema** per template drives the CLI flags, recipe files and the docs.
- **Recipes:** one TOML or JSON file describes a whole document, mixing page types
  ([docs/recipes.md](https://github.com/marcinkevicius/rmstrokes/blob/main/docs/recipes.md)).
- **Intro page:** an optional first page explaining how to use the document on the tablet, with small diagrams, a
  practice token, and each template's own steps and a miniature of its page.
- **Design system:** one set of type, colour, line and spacing tokens (`rmstrokes.design`), chosen per template with
  `--theme`. Two themes are built in: `default` (Atkinson Hyperlegible Next, greys tuned for the rM2) and `color`
  (the same, plus a soft Paper Pro palette). Another package can add its own with `design.register_theme`.
  `rmstrokes specimen` prints them ([docs/design-system.md](https://github.com/marcinkevicius/rmstrokes/blob/main/docs/design-system.md)).
- **Fonts:** three faces of Atkinson Hyperlegible Next are bundled, enough for every page. A font package (entry
  point group `rmstrokes.fonts`) or `fonts.add_font_source` can add more, found by name; the themes then use a
  display face for titles and a monospace for tabular numbers where one is installed.
- **Devices:** reMarkable 2 (checked on hardware), Paper Pro and Paper Pro Move (from published specs,
  **unverified**). Pages are sized to each device's pixel grid, 1 px = 72/dpi pt, so PDF and strokes line up.

## Install

Python 3.11 or later:

```bash
pipx install rmstrokes              # or: uv tool install rmstrokes
rmstrokes make gaps --intro -o gaps.rmdoc
```

Copy `gaps.rmdoc` to the tablet, open it, pick the "Words" layer in the layers menu, lasso a word and drag it.

PNG previews (`rmstrokes explain`, `specimen`, the gallery's pictures) also need pypdfium2:
`pipx install "rmstrokes[preview]"`. To work on rmstrokes itself, see [CONTRIBUTING.md](https://github.com/marcinkevicius/rmstrokes/blob/main/CONTRIBUTING.md).

## Usage

The example files live in this repository's [examples/](https://github.com/marcinkevicius/rmstrokes/tree/main/examples) folder.

```bash
rmstrokes make gaps --words sun --words rain --intro -o gaps.rmdoc   # one template, flags from its schema
rmstrokes make examples/templates/sorting.toml -o sorting.pdf  # a template file of your own (PDF: strokes printed)
rmstrokes build examples/reading.toml -o reading.rmdoc         # a recipe: intro, two gaps pages, a sorting page
rmstrokes make examples/character_mix/character_mix.py -o mix.rmdoc  # a Python template file with SVG art
rmstrokes templates                                            # what can be built (installed packages add their own)
rmstrokes params gaps                                          # a template's parameters
rmstrokes specimen -o specimen/                                # the design system on rm2 and pro (rmdoc, PDF, PNG)
rmstrokes gallery                                              # every template and example, for review (gallery.toml)
rmstrokes explain gaps -o explain/                             # how a page is built, step by step, as PNGs
```

`rmstrokes explain [TEMPLATE ...]` draws how a template's first page is built, in five pictures: what goes in
(parameter text, token shapes and SVGs), the layout in device pixels, one token becoming pen strokes, the layers,
and the finished page as `.rmdoc` and PDF. It writes a PNG per step plus the page itself (`--markdown FILE`: the
steps as a markdown page too). [docs/how-a-page-is-built.md](https://github.com/marcinkevicius/rmstrokes/blob/main/docs/how-a-page-is-built.md) is its output for `gaps`
and the character mix example, and the gallery shows it at the top of the contact sheet for the templates its
config lists under `explain`.

`rmstrokes gallery` builds every template (its defaults, with the intro page) and every example listed in a gallery
config, for the reMarkable 2 and the Paper Pro (`--with-move`: the Move too), as `.rmdoc`, `.pdf` and a PNG of the
first page, with an `index.html` contact sheet: the reMarkable 2 in the `default` design theme, the Paper Pro in
`color` (where a template has them), and the design system's specimen on each. It writes into a new
`~/rmstrokes-gallery/<date>-<time>-<commit>/` folder (`-o DIR`: a new or empty folder of your choice; `--dry-run`:
list and check only). This repository's [gallery.toml](https://github.com/marcinkevicius/rmstrokes/blob/main/gallery.toml) lists the examples; templates from installed
packages show up by themselves. The config format is in the docstring of `rmstrokes/gallery.py`.

From Python:

```python
from rmstrokes import Document, Layer, NameTag, Page, Rect, Token, get_device, grid_cells, token_art

dev = get_device("rm2")
art = token_art(Token("star", size_mm=10, number=1, name_tag=NameTag(width_mm=20)), dev)
cells = grid_cells(Rect(150, 1400, 1100, 400), 6, art.width + 20, art.height + 20)
strokes = [s for cell in cells for s in art.placed(*cell.center)]
page = Page(draw=lambda p: p.text("Stars", 150, 200, "AtkinsonHyperlegibleNext-SemiBold", 60, "#000000"),
            layers=[Layer("Tokens", strokes)], handwriting="Notes")
Document(dev, [page], title="Stars").write("stars.rmdoc")
```

Templates written in Python subclass `rmstrokes.Template` and are found through the `rmstrokes.templates` entry
point group, so another package can add its own (`name = "package.module:TEMPLATE"`), or are given by path as a
`.py` file that defines `TEMPLATE`.

## Documentation

| | |
|---|---|
| [docs/how-a-page-is-built.md](https://github.com/marcinkevicius/rmstrokes/blob/main/docs/how-a-page-is-built.md) | from text and SVGs to the finished page, step by step, in pictures (`rmstrokes explain`) |
| [docs/design-system.md](https://github.com/marcinkevicius/rmstrokes/blob/main/docs/design-system.md) | the design system: fonts, type scale, greys, Paper Pro colours, lines, knock-outs, spacing, themes, and why |
| [docs/intro.md](https://github.com/marcinkevicius/rmstrokes/blob/main/docs/intro.md) | the intro page: its cards and scenes, how to write a template's steps |
| [docs/templates.md](https://github.com/marcinkevicius/rmstrokes/blob/main/docs/templates.md) | template files: parameters, background elements, tokens, trays, layers, expressions |
| [docs/recipes.md](https://github.com/marcinkevicius/rmstrokes/blob/main/docs/recipes.md) | recipe files: one document from several templates |
| [docs/format-notes.md](https://github.com/marcinkevicius/rmstrokes/blob/main/docs/format-notes.md) | the `.rmdoc` and `.rm` v6 formats as we write them, what's verified |
| [docs/architecture.md](https://github.com/marcinkevicius/rmstrokes/blob/main/docs/architecture.md) | what the engine is made of: pipeline, modules, CLI and hooks, dependencies, files, format |
| [examples/](https://github.com/marcinkevicius/rmstrokes/tree/main/examples) | a recipe ([reading.toml](https://github.com/marcinkevicius/rmstrokes/blob/main/examples/reading.toml)), a template file ([templates/sorting.toml](https://github.com/marcinkevicius/rmstrokes/blob/main/examples/templates/sorting.toml)) and a Python template file with SVG art, [character_mix/](https://github.com/marcinkevicius/rmstrokes/tree/main/examples/character_mix) (build people from Open Peeps parts, CC0; Paper Pro and Move output unverified) |
| [CONTRIBUTING.md](https://github.com/marcinkevicius/rmstrokes/blob/main/CONTRIBUTING.md) | setting up, trying it on a tablet, pull requests |
| [CHANGELOG.md](https://github.com/marcinkevicius/rmstrokes/blob/main/CHANGELOG.md) | release notes |
| [SECURITY.md](https://github.com/marcinkevicius/rmstrokes/blob/main/SECURITY.md) | reporting a security problem |

## Development

`uv sync`, then `uv run pytest`. [CONTRIBUTING.md](https://github.com/marcinkevicius/rmstrokes/blob/main/CONTRIBUTING.md) has the rest; every font and image is listed in
[ATTRIBUTION.md](https://github.com/marcinkevicius/rmstrokes/blob/main/ATTRIBUTION.md).

## Acknowledgements and prior art

The `.rmdoc` and `.rm` v6 formats aren't officially documented. rmstrokes writes them with
**[rmscene](https://github.com/ricklupton/rmscene)**, and learnt them from open-source projects that read and write
them: [rmc](https://github.com/ricklupton/rmc), [rmrl](https://github.com/rschroll/rmrl),
[ddvk/rmapi](https://github.com/ddvk/rmapi), [drawj2d](https://sourceforge.net/p/drawj2d/wiki/reMarkable/) and the
[remarquee rmdoc package](https://pkg.go.dev/github.com/go-go-golems/remarquee/pkg/rmdoc).
[docs/format-notes.md](https://github.com/marcinkevicius/rmstrokes/blob/main/docs/format-notes.md) says what came from where. The character mix example uses
[Open Peeps](https://www.openpeeps.com/) by Pablo Stanley, and the pages are set in
[Atkinson Hyperlegible Next](https://github.com/googlefonts/atkinson-hyperlegible-next) by the Braille Institute.

## Licensing

- **The engine** (source, built-in template, examples, docs) is MIT ([LICENSE](https://github.com/marcinkevicius/rmstrokes/blob/main/LICENSE)).
- **Dependencies** are installed from PyPI, not bundled, and are under permissive licences: MIT, BSD or Apache-2.0
  (reportlab, rmscene, shapely, svgelements, numpy; the dev tools pytest, pypdf, pypdfium2, Pillow).
- **GEOS**, the geometry library inside shapely's wheels, is LGPL-2.1. rmstrokes uses it only through shapely, as
  the unmodified shared library shapely ships, so it can be swapped for another build; nothing of GEOS is in this
  repository.
- **Fonts**: Atkinson Hyperlegible Next Regular, Italic and SemiBold, unmodified, under the SIL Open Font License
  1.1. The licence text is next to them (`src/rmstrokes/fonts/OFL-AtkinsonHyperlegibleNext.txt`) and goes into the
  wheel. PDFs made with them embed font subsets; such documents are not themselves under the OFL.
- **Art**: the character parts in `examples/character_mix/parts/` are Open Peeps by Pablo Stanley, CC0 1.0.

Sources, versions and hashes of every non-code file are in [ATTRIBUTION.md](https://github.com/marcinkevicius/rmstrokes/blob/main/ATTRIBUTION.md).

## License

[MIT](https://github.com/marcinkevicius/rmstrokes/blob/main/LICENSE). See also [NOTICE](https://github.com/marcinkevicius/rmstrokes/blob/main/NOTICE) and [ATTRIBUTION.md](https://github.com/marcinkevicius/rmstrokes/blob/main/ATTRIBUTION.md).

"reMarkable" is a trademark of reMarkable AS; this project is not affiliated with or endorsed by reMarkable.
