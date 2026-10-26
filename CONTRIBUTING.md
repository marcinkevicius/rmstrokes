# Contributing

Thanks for taking a look! Bug reports, device reports, examples, docs fixes and small pull requests are all welcome.
Please be kind to each other ([Code of Conduct](CODE_OF_CONDUCT.md)); security problems go through
[SECURITY.md](SECURITY.md) rather than a public issue.

## The most useful thing: a Paper Pro or Move report

Only the **reMarkable 2** has been tried on a real tablet. If you have a **Paper Pro** or **Paper Pro Move**, build
`uv run rmstrokes make gaps --intro --device pro -o out/` (or `--device move`), put the `.rmdoc` on the tablet and
tell us how it went: do the strokes line up with the printed page, does a lasso pick up exactly one word, what does
the layers menu show? A photo says more than a description. There's a
[Device report](.github/ISSUE_TEMPLATE/device_report.yml) form for it.

## Setting up

You need Python 3.11+ and [uv](https://docs.astral.sh/uv/). No tablet needed: everything can be checked as a PDF or
PNG.

```sh
git clone https://github.com/marcinkevicius/rmstrokes.git
cd rmstrokes
uv sync            # rmstrokes, editable, plus the dev tools in .venv
uv run pytest      # the test suite, under a minute
```

Without uv: `python -m venv .venv && .venv/bin/pip install -e . pytest pypdf pypdfium2 pillow ruff`.

| Command | What it does |
|---|---|
| `uv run rmstrokes make gaps -o out/` | build one template (`out/` is git-ignored) |
| `uv run rmstrokes gallery` | build every template and example, with a contact sheet to look through |
| `uv run rmstrokes explain gaps -o out/explain` | how a page is built, step by step, as pictures |
| `uv build` | the wheel and sdist, into `dist/` |

[docs/architecture.md](docs/architecture.md) is a tour of the modules in `src/rmstrokes/`.

## Before you open a pull request

- One change per PR, with a test, and `uv run pytest` and `uv run ruff check` passing.
- Keep the built-in template and examples generic, and use only the public API in examples. Templates for a
  particular subject can live in a package of their own and plug in through the `rmstrokes.templates` entry point
  group.
- Fonts and art must be your own (MIT) or openly licensed (OFL, CC0 or similar), and listed in
  [ATTRIBUTION.md](ATTRIBUTION.md) with where they came from.
- A new template parameter goes in the template's `Schema`; the CLI flags, recipe keys and docs follow from it.
- If you change what goes into the `.rmdoc`, say which tablet you checked it on (or "unverified") and update
  [docs/format-notes.md](docs/format-notes.md).
- Don't commit generated `.rmdoc` or `.pdf` files. `tests/test_repo_hygiene.py` catches those, and paths from your
  machine; you can give it more patterns of your own in `.git/info/commit-patterns`, which never leaves your machine.
- PR titles follow [Conventional Commits](https://www.conventionalcommits.org/) (`feat:`, `fix:`, `docs:`, …),
  because the changelog is built from them. A line under *Unreleased* in [CHANGELOG.md](CHANGELOG.md) is nice for
  anything people will notice.

By contributing, you agree that your contribution is released under the project's [MIT licence](LICENSE).

## Examples

An example is a recipe, a template file or a folder in `examples/`. Say in a comment how to build it, add it to
`gallery.toml`, and add a test that builds it on every device. Keep its content inside the page's safe area
(`Style.safe_area()`), clear of the toolbar; `tests/test_safe_area.py` checks.

## Releases

Releases are made with [release-please](https://github.com/googleapis/release-please): it keeps a release PR open with
the next version and changelog, and merging it tags the release. Before `1.0.0`, a minor version may change the API.
