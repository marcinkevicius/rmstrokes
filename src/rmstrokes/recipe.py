"""Recipe files: one TOML or JSON file describes a whole document, page section by section.

    name = "Reading practice"    # document name on the tablet, and the file name stem
    device = "rm2"
    intro = true                 # start with the how-to page
    theme = "color"              # for every section whose template has a theme of that name

    [[pages]]                    # a section: one template, its parameters, and copies
    template = "gaps"
    words = ["sun", "rain"]

    [[pages]]
    template = "my-page.toml"    # a template file, relative to the recipe
    copies = 3                   # the section's pages, three times over

Each section is checked against its template's schema, so a typo or a bad value is reported with
the section and parameter it is in. Sections may use different templates; they must share one
orientation (a reMarkable document is either portrait or landscape).
"""
from __future__ import annotations

import json
import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Sequence

from .devices import Device, device_key, get_device
from .intro import IntroSpec, intro_page
from .layers import Document
from .params import SchemaError
from .templates import Template, get_template

DOCUMENT_KEYS = ("name", "device", "intro", "theme", "pages")
DOCUMENT_ONLY = ("device", "name", "intro")


@dataclass
class Section:
    template: Template
    values: dict[str, Any]  # validated: common and template parameters
    where: str = ""


@dataclass
class Recipe:
    name: str | None
    device: str
    intro: bool
    sections: list[Section]
    source: Path | None = None

    @property
    def stem(self) -> str:
        return self.name or (self.source.stem if self.source else "document")


def read_recipe_file(path: Path) -> dict[str, Any]:
    path = Path(path)
    text = path.read_text(encoding="utf-8")
    try:
        if path.suffix.lower() == ".json":
            return json.loads(text)
        return tomllib.loads(text)
    except (json.JSONDecodeError, tomllib.TOMLDecodeError) as e:
        raise SchemaError(f"{path.name}: {e}") from None


def load_recipe(path: Path | str, *, device: str | None = None, allow_python: bool = False) -> Recipe:
    """A recipe file. It may name Python template files only with `allow_python`: they are code."""
    path = Path(path)
    return recipe_from_dict(read_recipe_file(path), path.name, base=path.parent, device=device,
                            source=path, allow_python=allow_python)


def recipe_from_dict(data: dict[str, Any], where: str = "recipe", *, base: Path | None = None,
                     device: str | None = None, source: Path | None = None,
                     allow_python: bool = False) -> Recipe:
    if not isinstance(data, dict):
        raise SchemaError(f"{where}: expected a table of document settings and [[pages]]")
    if bad := sorted(set(data) - set(DOCUMENT_KEYS)):
        raise SchemaError(f"{where}: unknown key(s) {', '.join(bad)} at the top (known: "
                          f"{', '.join(DOCUMENT_KEYS)}; template parameters go in a [[pages]] section)")
    try:
        dev = device_key(device or data.get("device", "rm2"))
    except ValueError as e:
        raise SchemaError(f"{where}: device: {e}") from None
    name = data.get("name")
    if name is not None and not isinstance(name, str):
        raise SchemaError(f"{where}: name: expected text, got {name!r}")
    intro = data.get("intro", False)
    if not isinstance(intro, bool):
        raise SchemaError(f"{where}: intro: expected true or false, got {intro!r}")
    sections_raw = data.get("pages")
    if not sections_raw or not isinstance(sections_raw, list):
        raise SchemaError(f"{where}: no [[pages]] sections; add at least one, e.g.\n"
                          '  [[pages]]\n  template = "gaps"')
    templates = []
    for i, raw in enumerate(sections_raw, 1):
        if not isinstance(raw, dict) or "template" not in raw:
            raise SchemaError(f"{where}: pages[{i}]: each section needs a template = \"...\"")
        try:
            templates.append(get_template(raw["template"], base, allow_python=allow_python))
        except SchemaError as e:
            raise SchemaError(f"{where}: pages[{i}]: {e}") from None
    theme = data.get("theme")
    if theme is not None and not any(theme in t.themes() for t in templates):
        known = "; ".join(f"{t.name}: {', '.join(t.themes())}" for t in dict.fromkeys(templates))
        raise SchemaError(f"{where}: theme {theme!r} is not a theme of any template in this recipe ({known})")
    sections = []
    for i, (raw, template) in enumerate(zip(sections_raw, templates), 1):
        sw = f"{where}: pages[{i}]"
        values = {k: v for k, v in raw.items() if k != "template"}
        for key in DOCUMENT_ONLY:
            if key in values:
                raise SchemaError(f"{sw}: {key!r} is set once for the whole document, at the top of the recipe")
        if "theme" not in values and "theme" in data and data["theme"] in template.themes():
            values["theme"] = data["theme"]
        values = template.validate({**values, "device": dev, "name": name}, f"{sw} ({template.name})")
        sections.append(Section(template, values, sw))
    return Recipe(name, dev, intro, sections, source)


def build_document(sections: Sequence[Section], device: Device | str, *, name: str | None = None,
                   intro: bool = False) -> Document:
    """The document: the intro page (if asked for), then each section's pages, `copies` times."""
    device = get_device(device)
    if not sections:
        raise SchemaError("nothing to build: no sections")
    pages, firsts = [], []
    for sec in sections:
        ctx = sec.template.context(device, sec.values["theme"], name)
        built = sec.template.pages(sec.values, ctx)
        if not built:
            raise SchemaError(f"{sec.where or sec.template.name}: the template made no pages")
        firsts.append((sec.template, sec.values, built[0]))
        pages += built * sec.values.get("copies", 1)
    if intro:
        seen, parts = set(), []
        for template, values, first in firsts:
            if template.name not in seen:
                seen.add(template.name)
                spec = template.intro_spec(values) or IntroSpec(template.title or template.name)
                parts.append((spec, first))
        title = name or sections[0].template.title or sections[0].template.name
        first, values = sections[0].template, sections[0].values
        style = first.style_for(values["theme"], device)
        pages.insert(0, intro_page(device, parts, landscape=pages[0].landscape, title=title, style=style))
    first, values = sections[0].template, sections[0].values
    meta = first.document_meta(values, first.context(device, values["theme"], name))
    doc = Document(device, pages, title=name or first.default_title or first.default_name, **meta)
    try:
        doc.landscape  # one orientation per document
    except ValueError as e:
        raise SchemaError(str(e)) from None
    return doc


def build_recipe(recipe: Recipe) -> Document:
    return build_document(recipe.sections, recipe.device, name=recipe.name, intro=recipe.intro)
