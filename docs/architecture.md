# How rmstrokes is put together

What the engine is made of: the pipeline, its modules, the CLI and the hooks for other packages, its dependencies
and bundled files, what it reads and writes, and where it touches the reMarkable file format.

## 1. What it is

rmstrokes is a Python library and CLI (MIT, Python 3.11+) that writes notebooks for reMarkable tablets in which
the fixed part of a page is a vector PDF and the parts people move are real pen strokes on named layers. You
describe a page as a template (TOML data or a Python class) with one parameter schema; the engine turns shapes and
SVGs into compact stroke clusters (one lasso takes one object), places them as tokens in grids, draws the
background with reportlab and packs everything into an `.rmdoc` the tablet opens like any notebook, or into a plain
PDF with the strokes printed for checking. Only the reMarkable 2 has been checked on hardware; Paper Pro and Paper
Pro Move output is **unverified**.

Pipeline:

```
shapes / SVG ──vectorize──▶ strokes ──tokens──▶ token art (shape + label + name tag, one cluster)
                                                   │ trays: a grid of slots (geometry.grid_cells)
template (TOML or Python, one Schema) ──▶ pages: PDF background (pdf.Painter) + named stroke layers (layers)
recipe (several templates, copies, intro page) ──▶ Document ──▶ .rmdoc (rmdoc + rm via rmscene) or PDF
```

Out of the box: one built-in template (`gaps`, fill in the gaps), two design themes (`default`, `color`), three
bundled fonts, the intro page, the specimen, `explain` and the gallery. Other packages can add templates, themes and
fonts through the hooks in section 3.

## 2. Modules

Lines are of `src/rmstrokes/*.py` (about 6,500 in total with docstrings). "Used by" is inside the engine; anything
listed in `__init__.__all__` is also the public API for other packages.

| Module | Lines | Purpose | Public API | Depends on (engine) | Used by |
|---|---:|---|---|---|---|
| `__init__` | 26 | re-exports the public API, `__version__` | the names in `__all__` | most modules | users |
| `devices` | 66 | device presets (canvas px, dpi, colour, verified flag) | `Device`, `DEVICES`, `get_device`, `device_key` | none | nearly everything |
| `geometry` | 117 | page px vs `.rm` coordinates, `Rect`, rotation, grids of cells | `Rect`, `grid_cells`, `FitError`, `page_size`, `to_rm`, `from_rm` | devices | pdf, layers, tokens, datatemplate, design, intro, ... |
| `vectorize` | 366 | SVG to strokes: parse, composite fills (shapely), contour + hatch, thin-feature patching | `Stroke`, `Art`, `load_art`, `art_strokes`, `hatch`, `contours` | none | rm, shapes, tokens, layers, intro, specimen, strokefont |
| `shapes` | 85 | primitive shapes (circle, star, pin, tag, arrow, ...) as regions, regions as strokes | `unit_shape`, `shape_region`, `region_strokes` | vectorize | tokens |
| `strokefont` | 118 | a single-line stroke font (capitals, digits) so labels move with tokens | `text_strokes`, `glyph_strokes`, `missing_glyphs` | vectorize | tokens, specimen |
| `tokens` | 230 | a token: shape/SVG + icon, label or number + optional name tag, one cluster | `Token`, `NameTag`, `TokenArt`, `token_art` | devices, geometry, shapes, strokefont, vectorize | datatemplate, intro, specimen |
| `fields` | 101 | write-in fields (label + ruled line/box) on the background | `WriteIn`, `FieldStyle`, `draw_write_in` | fonts, geometry, pdf | datatemplate, specimen |
| `fonts` | 92 | font lookup (bundled + registered folders + font packages), reportlab registration, metrics | `font`, `font_path`, `add_font_source`, `text_width` | none | pdf, layers, design, fields, intro, datatemplate |
| `pdf` | 181 | `Painter`: reportlab canvas in device px, y down; strokes printed into a PDF | `Painter`, `draw_strokes` | devices, fonts, geometry | layers, fields, intro, specimen, datatemplate |
| `rm` | 121 | v6 `.rm` page writer and reader (through rmscene) | `rm_page`, `read_layers` | devices, vectorize | layers |
| `rmdoc` | 148 | `.rmdoc` zip: `.content`, `.metadata`, PDF, one `.rm` per page; reader | `write_rmdoc`, `read_rmdoc`, `RmdocIds` | none | layers |
| `layers` | 202 | the layer API: `Page` (background + layers + handwriting layer), `Document.write` | `Document`, `Page`, `Layer`, `DocumentResult` | devices, fonts, geometry, pdf, rm, rmdoc, vectorize | recipe, run, templates, intro, specimen, datatemplate |
| `design` | 400 | design tokens: type roles, greys, Paper Pro palette, lines, spacing; themes `default`, `color` (others through `register_theme`); contrast maths | `Style`, `get_style`, `THEMES`, `register_theme`, `contrast`, `delta_e` | devices, fonts, geometry | templates, datatemplate, intro, specimen, gallery, cli |
| `params` | 304 | one parameter schema drives CLI flags, recipe validation and docs | `Param`, `Schema`, `SchemaError` | none | templates, recipe, datatemplate, gallery, cli |
| `expr` | 97 | safe arithmetic in template files (AST whitelist) | `number`, `fill` | none | datatemplate |
| `templates` | 289 | `Template` base, registry: built-ins, entry points, files by path or name | `Template`, `Context`, `register`, `register_file`, `get_template`, `available_templates` | datatemplate, design, devices, layers, params | recipe, run, gallery, cli |
| `datatemplate` | 676 | TOML templates: params, `[let]` names, background elements (text, passages with gaps, shapes, fields), tokens, grid trays, layers | `load_template_file`, `DataTemplate` | most drawing modules, expr | templates |
| `intro` | 728 | the optional "how to use it" first page: six illustrated cards, a practice token, the template's own steps and a miniature | `IntroSpec`, `intro_page`, `token_maker` | design, devices, fonts, geometry, layers, pdf, tokens, vectorize | recipe, datatemplate |
| `recipe` | 160 | one TOML/JSON file -> one document from several template sections | `Recipe`, `Section`, `load_recipe`, `build_recipe`, `build_document` | devices, intro, layers, params, templates | run, gallery, cli |
| `run` | 97 | a template's command line generated from its schema | `template_main`, `add_template_arguments`, `run_template` | devices, layers, recipe, templates | cli |
| `specimen` | 454 | the design system's specimen document (+ PNG via pypdfium2) | `specimen_document`, `write_specimens` | design, devices, fields, geometry, layers, pdf, strokefont, tokens, vectorize | cli, gallery |
| `explain` | 652 | how a page is built in five pictures (inputs, layout, strokes, layers, finished) from a template's real page; the steps' text for the CLI, gallery and docs | `explain`, `Explainer`, `Step`, `write_explainers`, `markdown` | design, devices, fonts, geometry, layers, pdf, recipe, shapes, templates, tokens, vectorize | cli, gallery |
| `gallery` | 572 | builds every template + example on several devices with an HTML contact sheet | `load_gallery`, `run_gallery`, `build_job`, `Entry`, `Job` | design, devices, params, recipe, specimen, templates | cli |
| `cli` | 246 | the `rmstrokes` command | `main`, `add_build_arguments` | most | console script |

Data and assets in the package: `builtin/gaps.toml` (the built-in template), `fonts/` (3 TTFs + 1 OFL text).

`Page.meta["areas"]` and `Page.meta["placements"]` (`tokens.Placement`) are how a template tells `explain` its
layout boxes and where each token went; data templates fill them, Python templates may.

## 3. CLI commands and hooks for other packages

| Command | What it does |
|---|---|
| `rmstrokes build RECIPE [--device D\|all] [-o OUT] [--format rmdoc\|pdf]` | one document from a recipe file |
| `rmstrokes make TEMPLATE [flags] [-o OUT]` | one template; its flags come from its schema; TEMPLATE is a name or a `.toml`/`.py` path |
| `rmstrokes templates` | lists every template and where it comes from |
| `rmstrokes params NAME [--recipe]` / `--all` | a template's parameters as markdown (or a `[[pages]]` snippet); `--all` for the docs |
| `rmstrokes devices` | the device presets, with the unverified ones marked |
| `rmstrokes specimen [--device] [--theme] [-o DIR] [--no-png]` | the design-system specimen (rmdoc + PDF + PNG) |
| `rmstrokes gallery [CONFIG] [-o DIR] [--with-move] [--only GROUP] [--dry-run]` | every template and example, with `index.html` |
| `rmstrokes explain [TEMPLATE ...] [--device D\|all] [-o DIR] [--markdown FILE] [--no-documents]` | how a page is built: a PNG per step and the page as `.rmdoc` + PDF |
| `rmstrokes --version` | version |

Every template flag set also has `--device`, `--theme`, `--name`, `--copies`, `--intro`, `-o`, `--format`.

Hooks for other packages:

- **`rmstrokes.templates` entry point group** (`name = "package.module:TEMPLATE"`): the way an external package
  adds templates. They appear in `templates`, `make`, recipes and the gallery without any config.
- **`design.register_theme(name, factory)`**: adds a design theme; `--theme`, recipes, `get_style` and the specimen
  accept it from then on ([design-system.md](design-system.md#themes)).
- **`fonts.add_font_source(fn)`**: an external package can add font folders (searched before the bundled fonts).
- **Entry point group `rmstrokes.fonts`**: an installed font package names a callable returning its font folders
  (searched after registered sources, before the bundled fonts), loaded on the first lookup, so its fonts are found by
  name without importing it. The built-in themes' title, small and numeric roles use such fonts when present and
  fall back to the bundled Atkinson faces (`design.FALLBACK`).
- **`DataTemplate` subclasses** can add tray kinds and keys (`tray_kinds`, `tray_keys`, `_tray_cells`, `_tray_call`).
- **`templates.register()` / `register_file()`**, `run.template_main()` and `cli.add_build_arguments()` for other
  CLIs to reuse.
- **Console script `rmstrokes`** (`rmstrokes.cli:main`); gallery `command` entries look up *any* installed console
  script by name and call it in-process.
- **Template files by path**: a `.py` file is *executed* (it must define `TEMPLATE`); a `.toml` file is data.

## 4. Dependencies and bundled files

Runtime (in `pyproject.toml`): reportlab >= 4.2 (BSD; pulls in Pillow, MIT-CMU, and charset-normalizer, MIT),
**rmscene == 0.8.0** (MIT; pulls in packaging, Apache-2.0/BSD), shapely >= 2.0 (BSD-3-Clause; its wheels bundle
GEOS, LGPL-2.1, as a shared library), svgelements >= 1.9.6 (MIT), numpy >= 1.26 (BSD-3-Clause and compatible).
Development group: pytest (MIT), pypdf (BSD-3-Clause), pypdfium2 (Apache-2.0 / BSD-3-Clause; bundles PDFium),
Pillow (MIT-CMU). The licence position is summed up in the README's [Licensing](../README.md#licensing) section.

Bundled files (sources and SHA-256 in [ATTRIBUTION.md](../ATTRIBUTION.md)):

| Files | Licence |
|---|---|
| Atkinson Hyperlegible Next Regular, Italic, SemiBold (`src/rmstrokes/fonts/`, 200 KB) | SIL OFL 1.1, unmodified upstream files, licence text next to them |
| Open Peeps parts (`examples/character_mix/parts/`) | CC0 1.0 |
| Preview PNGs in `docs/` | rendered by the engine, MIT |
| Built-in template, examples | original, MIT |

`.gitignore` ignores fonts everywhere except `src/rmstrokes/fonts/*.ttf`, and generated `.rmdoc`, `.pdf` and `.zip` files everywhere.

## 5. Files, network, telemetry

- **Reads:** template files (`.toml`, `.py`), recipe files (`.toml`, `.json`), SVGs a template names, its own
  bundled fonts and built-ins, fonts in folders an external package registers or an installed font package names,
  the gallery config.
- **Executes:** Python template files given by path or found next to a recipe; gallery `command` entries (installed
  console scripts); `git rev-parse` / `git status` in the gallery config's folder, only to name the output folder.
  Running `rmstrokes build` on a recipe folder you downloaded runs the Python template files in it: treat such a
  folder like any other code.
- **Writes:** only where told: `-o` (file or folder; default the current folder), `rmstrokes specimen` defaults to
  `./specimen/`, `rmstrokes gallery` defaults to a new `~/rmstrokes-gallery/<date>-<time>-<commit>/` and never
  writes into a non-empty folder. No config files, caches or temp files are written elsewhere.
- **Network:** none. No module imports `urllib`, `http`, `socket`, `requests` or similar; no update checks.
- **Telemetry:** none.
- `.metadata` gets the current time as `lastModified`. Document and page ids are random UUIDs by default;
  the gallery and the specimen pass a seed, so their rebuilds get the same ids (uuid5 of
  `Template.seed_namespace` and the seed).

## 6. The reMarkable file format

Everything that touches the tablet's format is in three modules plus the stroke properties:

| Part | Where | How it's done | Stability |
|---|---|---|---|
| `.rmdoc` zip (`.content`, `.metadata`, PDF, `<page>.rm`) | `rmdoc.py` | written by hand from observed files (formatVersion 2, "cPages") | reverse engineered, firmware 3.x; fields marked unverified in [format-notes.md](format-notes.md) |
| `.rm` v6 pages: blocks, scene tree, layers, lines | `rm.py` | rmscene's block classes, layout copied from its device fixtures | depends on rmscene internals (`scene_stream`, `crdt_sequence`, `tagged_block_common`), hence the **exact pin `rmscene==0.8.0`** |
| pen, colour, width, point fields | `vectorize.py`, `shapes.py`, `tokens.py`, `design.py`, `pdf.py` | rmscene `scene_items` enums (fineliner, `PenColor`) | public rmscene API, fairly stable |
| device canvases and the PDF/stroke alignment | `devices.py`, `geometry.py` | published specs; rM2 checked on hardware | Paper Pro and Move **unverified** |

Risks: a firmware update can change `.content` or `.rm` versions; rmscene may change its private modules in a
minor release, so bump the pin only with the round-trip tests (`tests/test_devices_and_rmdoc.py`, the `read_layers`
checks) and a device check. The format notes credit their sources (rmscene, rmc, public write-ups).
