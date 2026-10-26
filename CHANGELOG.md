# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project follows [Semantic Versioning](https://semver.org/spec/v2.0.0.html). Before `1.0.0`, any minor release may contain breaking changes.

## [0.1.0](https://github.com/marcinkevicius/rmstrokes/compare/v0.1.0...v0.1.0) (2026-10-26)


### Added

* initial release of rmstrokes 0.1.0 ([d394689](https://github.com/marcinkevicius/rmstrokes/commit/d394689540748224ac28e27d019b46569da7f714))

## [Unreleased]

Initial public release of rmstrokes, as `0.1.0`.

### Added

- SVG and primitive shapes (circle, star, pin, tag, arrow, …) to fineliner pen strokes: a contour along the edge, a scanline hatch inside, thin features patched; filled, grey, outline or over opaque white ink. Each object is one compact cluster, so one lasso takes exactly one object.
- Layer API: a page is one vector PDF background plus any number of named stroke layers and an optional empty handwriting layer (`Page`, `Layer`, `Document`), written as an `.rmdoc` or as a PDF with the strokes printed.
- Tokens with an optional icon, label or number and a blank name tag that moves with them; trays of slots (`grid_cells`); write-in fields.
- Templates as data: TOML template files with parameters, background elements, tokens, trays and expressions; Python templates (`rmstrokes.Template`) found through the `rmstrokes.templates` entry point group or by path. Built in: `gaps` (fill in the gaps).
- One parameter schema per template drives the CLI flags, recipe keys and docs.
- Recipes: one TOML or JSON file describes a whole document from several templates.
- Shared files stay data: a recipe uses a Python template file only with `--allow-python`, and a template file reads SVGs only from its own folder.
- An optional intro page explaining how to use the document on the tablet.
- A design system (type, colour, line and spacing tokens) with two themes, `default` and `color`; `register_theme` for other packages.
- A safe area per device (`Style.safe_area()`, and `safe_x`, `safe_y`, `safe_w`, `safe_h` in template files): inside the margin and clear of the strip the open toolbar covers. The intro page, the built-in template and the examples stay inside it, checked by a test on every device.
- Three bundled faces of Atkinson Hyperlegible Next; more fonts through the `rmstrokes.fonts` entry point group or `add_font_source`.
- Devices: reMarkable 2 (checked on hardware), Paper Pro and Paper Pro Move (from published specs, unverified).
- CLI: `make`, `build`, `templates`, `params`, `specimen`, `gallery` (every template and example as `.rmdoc`, `.pdf` and PNG with a contact sheet) and `explain` (how a page is built, step by step).
- Examples: a recipe, a TOML template file, and a Python template with Open Peeps SVG art (CC0).
- Documentation: architecture, templates, recipes, intro page, design system, `.rmdoc`/`.rm` format notes, and how a page is built.
- MIT licence, attribution of every font and image, a contributing guide, and CI on Python 3.11–3.13.
