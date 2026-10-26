# Recipe files

A recipe describes a whole document: a few document settings, then one `[[pages]]` section per run of pages. Each
section names a template and sets its parameters; sections may use different templates.

```toml
name = "Reading practice"  # document name on the tablet, and the file name stem
device = "rm2"             # rm2 | pro | move (or an alias); --device on the command line overrides it
intro = true               # start with the how-to page (default false)
theme = "default"          # optional: for every section whose template has a theme of that name

[[pages]]
template = "gaps"          # a template name, or a template file relative to this recipe
                           # (a name may also be a file next to the recipe: "my-page" -> my_page.toml)
title = "At the market"
text = "We walked to the ___ with a big basket and bought a loaf of ___."
words = ["bread", "market", "rain"]

[[pages]]
template = "templates/sorting.toml"
groups = ["Fruit", "Vegetable"]
copies = 3                 # this section's pages three times over (identical copies)
```

A recipe may also name a Python template file (`template = "my_page.py"`). That file is code and runs when the
document is built, so `rmstrokes build` refuses it unless you pass `--allow-python` (in Python:
`load_recipe(path, allow_python=True)`). Only allow it for files you trust.

```bash
rmstrokes build reading.toml -o reading.rmdoc
rmstrokes build reading.toml --device all -o out/     # one file per device
rmstrokes build reading.toml -o check.pdf             # a PDF with the strokes printed, to look at
```

The same file as JSON (`.json`): `{"name": "Reading practice", "intro": true, "pages": [{"template": "gaps", ...}]}`.
[examples/reading.toml](../examples/reading.toml) is a complete one.

## Rules

- **Document settings** (`name`, `device`, `intro`) are set once, at the top; a section can't set them. `theme` at
  the top applies to the sections whose template has that theme; a section's own `theme` must be one of its
  template's. A top-level theme no section's template knows is an error (a typo, usually).
- **Copies:** `copies = N` repeats the section's pages N times, identical (each a page of its own on the tablet).
- **Intro page:** with `intro = true` the document starts with one page: the generic steps (select the layer, lasso,
  drag, write in a name tag, show and hide layers), with diagrams and a practice token, then each template's own
  steps and a miniature of its first page.
- **One orientation per document:** a reMarkable document is portrait or landscape. Sections whose templates differ
  (a landscape sheet after portrait pages) are refused with the page numbers; make two documents.
- **Errors** name the file, the section and the parameter: `reading.toml: pages[1] (gaps): copies: must be at
  least 1 (got 0)`. Nothing is written until the whole recipe is valid.

Every template's parameters: `rmstrokes params <template>` (or `--recipe` for a section to copy, with the defaults).
