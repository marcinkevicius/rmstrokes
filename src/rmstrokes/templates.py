"""Templates: something that turns parameter values into pages.

A template declares its parameters once (params.Schema); every template also takes the common
document parameters below. Templates come from three places:

- Python templates registered with ``register()``, or installed by another package through the
  ``rmstrokes.templates`` entry point group (``name = "package.module:TEMPLATE"``);
- data templates (TOML files, see datatemplate.py), the built-in ones in rmstrokes/builtin/;
- any template file given by path: a TOML data template, or a Python file that defines
  ``TEMPLATE`` (a Template instance or subclass), so an example can live next to its assets.
  A file registered with ``register_file()`` is also found by name (its stem, ``_`` read as
  ``-``), and so is one next to a recipe: ``template = "my-page"`` finds
  ``my_page.py`` in the recipe's folder.
"""
from __future__ import annotations

import hashlib
import importlib.util
import sys
from dataclasses import dataclass
from functools import cache
from importlib import metadata
from pathlib import Path
from typing import Any

from . import design
from .devices import ALIASES, DEVICES, Device, device_key
from .layers import Document, DocumentResult, Page
from .params import Param, Schema, SchemaError

ENTRY_POINT_GROUP = "rmstrokes.templates"
BUILTIN_DIR = Path(__file__).resolve().parent / "builtin"
COMMON_NAMES = ("device", "theme", "name", "copies", "intro")


@dataclass(frozen=True)
class Context:
    """What a template builds pages for. `style` is the theme's design tokens for the device
    (design.Style); builders pass the one the template maps its theme to (Template.style_for),
    otherwise it comes from the theme name, a theme that isn't a design theme getting `default`."""

    device: Device
    theme: str
    name: str | None = None
    style: design.Style | None = None

    def __post_init__(self):
        if self.style is None:
            theme = self.theme if self.theme in design.THEMES else "default"
            object.__setattr__(self, "style", design.get_style(theme, self.device))


def device_arg(name: str) -> str:
    """argparse type for --device: a device key or alias, or "all"."""
    import argparse
    if name == "all":
        return name
    try:
        return device_key(name)
    except ValueError as e:
        raise argparse.ArgumentTypeError(str(e)) from None


class Template:
    """Base class for Python templates; override `pages` (and what else differs)."""

    name: str = ""
    title: str = ""
    description: str = ""
    params: Schema = Schema()
    intro = None                 # intro.IntroSpec: this template's part of the intro page
    default_theme: str = "default"
    theme_help: str = ("default: the design system (greyscale); color: with Paper Pro colours "
                       "(unverified on device)")
    # This template's own theme names -> the design theme (design.THEMES) they draw with, for
    # templates whose themes aren't the design themes (a theme not listed and not a design theme
    # draws with `fallback_style`).
    theme_styles: dict[str, str] = {}
    fallback_style: str = "default"
    # The theme for colour devices where it isn't the design theme "color" (gallery, say).
    color_theme: str | None = None
    default_name: str = "document"   # file name stem without --name
    default_title: str | None = None  # document name on the tablet without --name (None: the stem)
    creator: str = "rmstrokes"
    seed_namespace: str = "rmstrokes"  # for reproducible ids (layers.Document.write_rmdoc)
    initial_font: str | None = None  # the tablet's text tool font (None: the style's body font)

    def themes(self) -> list[str]:
        return list(design.THEMES)

    def style_for(self, theme: str, device: Device) -> design.Style:
        """The design tokens pages of this template in `theme` are drawn with."""
        name = self.theme_styles.get(theme, theme)
        return design.get_style(name if name in design.THEMES else self.fallback_style, device)

    def context(self, device: Device, theme: str, name: str | None = None) -> Context:
        return Context(device, theme, name, self.style_for(theme, device))

    def landscape(self, values: dict[str, Any]) -> bool:
        return False

    def intro_spec(self, values: dict[str, Any]):
        """This template's part of the intro page for these values (default: `intro`)."""
        return self.intro

    def pages(self, values: dict[str, Any], ctx: Context) -> list[Page]:
        raise NotImplementedError

    def document_meta(self, values: dict[str, Any], ctx: Context) -> dict[str, Any]:
        """Document fields when this template's section comes first: creator, subject, fonts,
        initial_font (see layers.Document)."""
        return {"creator": self.creator, "subject": f"{ctx.device.name}, {self.title or self.name}",
                "initial_font": self.initial_font or ctx.style.font("body")}

    def summary(self, result: DocumentResult, doc: Document, values: dict[str, Any], ctx: Context) -> str:
        strokes = sum(len(p.strokes) for p in doc.pages)
        return (f"{result.path}: {ctx.device.name}, {len(doc.pages)} page(s), {strokes} strokes, "
                f"{result.size_kib():.1f} KiB")

    def written(self, result: DocumentResult, doc: Document, values: dict[str, Any], ctx: Context):
        """Called after the document is written (extra outputs, previews)."""

    # ------------------------------------------------------------------ schema

    def common(self) -> Schema:
        return common_schema(self)

    @property
    def schema(self) -> Schema:
        return self.common() + self.params

    def validate(self, values: dict[str, Any], where: str | None = None) -> dict[str, Any]:
        return self.schema.validate(values, self.name if where is None else where)


def common_schema(t: Template) -> Schema:
    return Schema((
        Param("device", "str", "rm2", f"{', '.join(DEVICES)} (aliases: {', '.join(ALIASES)})",
              convert=device_key, argtype=device_arg, metavar="DEVICE"),
        Param("theme", "str", t.default_theme, t.theme_help, choices=t.themes),
        Param("name", "str", None, "document name shown on the tablet, and the file name stem"),
        Param("copies", "int", 1, "how many times to repeat the pages (identical copies)", min=1,
              metavar="N"),
        Param("intro", "bool", False, "start with a page on how to use the document on the tablet"),
    ))


# --------------------------------------------------------------------------- registry

_registry: dict[str, Template] = {}
_files: dict[str, Path] = {}
FILE_SUFFIXES = (".py", ".toml")


def register(template: Template) -> Template:
    if not template.name:
        raise ValueError("a template needs a name")
    _registry[template.name] = template
    return template


def file_template_name(path: Path) -> str:
    """The name a template file is found by: its stem, `_` read as `-` (my_page.py: my-page)."""
    return Path(path).stem.replace("_", "-")


def register_file(path: Path | str) -> str:
    """Make a template file (not installed: an example, say) available by name; loaded when first
    asked for. Returns the name."""
    path = Path(path).expanduser().resolve()
    if path.suffix not in FILE_SUFFIXES or not path.is_file():
        raise SchemaError(f"template file {path} not found (a .py or .toml template)")
    name = file_template_name(path)
    _files[name] = path
    return name


def _load_file(name: str, path: Path) -> Template:
    template = get_template(str(path))
    if template.name != name:
        raise SchemaError(f"{path.name} defines template {template.name!r}, not {name!r}: name the file "
                          f"{template.name.replace('-', '_')}{path.suffix}")
    return register(template)


def _sibling_file(name: str, base: Path) -> Path | None:
    """A template file named after `name` in the recipe's folder."""
    for stem in dict.fromkeys((name, name.replace("-", "_"))):
        for suffix in FILE_SUFFIXES:
            if (path := base / f"{stem}{suffix}").is_file():
                return path
    return None


def _entry_points() -> dict[str, metadata.EntryPoint]:
    return {ep.name: ep for ep in metadata.entry_points(group=ENTRY_POINT_GROUP)}


def _builtin_files() -> dict[str, Path]:
    return {p.stem: p for p in sorted(BUILTIN_DIR.glob("*.toml"))}


def available_templates() -> dict[str, str]:
    """name -> where it comes from."""
    out = {name: f"{ep.value} (installed)" for name, ep in _entry_points().items()}
    out.update({name: str(p) for name, p in _builtin_files().items()})
    out.update({name: str(p) for name, p in _files.items()})
    out.update({name: f"{type(t).__module__} (registered)" for name, t in _registry.items()
                if name not in _files})
    return dict(sorted(out.items()))


def template_origin(name: str) -> str:
    """Where a template name comes from: installed, builtin, file (register_file) or registered."""
    if name in _entry_points():
        return "installed"
    if name in _builtin_files():
        return "builtin"
    if name in _files:
        return "file"
    if name in _registry:
        return "registered"
    raise SchemaError(f"unknown template {name!r}")


def _no_python(path: Path) -> SchemaError:
    return SchemaError(f"{path.name} is a Python template file, and building it runs its code; that needs "
                       "--allow-python (rmstrokes build) or allow_python=True. Only allow it for files you trust.")


def get_template(name_or_path: str | Path | Template, base: Path | None = None, *,
                 allow_python: bool = True) -> Template:
    """A registered or installed template by name, a built-in data template, a registered template
    file, or a template file (a path, relative to `base` if given). With `base`, a name not found
    otherwise may also be a template file in that folder (`my-page`: my_page.py). With
    `allow_python=False` (recipes, unless trusted), a .py template file is refused: it is code."""
    if isinstance(name_or_path, Template):
        return name_or_path
    name = str(name_or_path)
    if name.endswith((".toml", ".py")) or "/" in name:
        path = Path(name).expanduser()
        if base is not None and not path.is_absolute():
            path = base / path
        if not path.is_file():
            raise SchemaError(f"template file {path} not found")
        if path.suffix == ".py":
            if not allow_python:
                raise _no_python(path)
            return load_python_template(path.resolve())
        from .datatemplate import load_template_file
        return load_template_file(path)
    if name in _registry:
        return _registry[name]
    if ep := _entry_points().get(name):
        obj = ep.load()
        template = obj() if isinstance(obj, type) else obj
        return register(template)
    if path := _builtin_files().get(name):
        from .datatemplate import load_template_file
        return register(load_template_file(path))
    if path := _files.get(name):
        return _load_file(name, path)
    if base is not None and (path := _sibling_file(name, Path(base))):
        if path.suffix == ".py" and not allow_python:
            raise _no_python(path)
        return _load_file(name, path.resolve())
    raise SchemaError(f"unknown template {name!r}; available: {', '.join(available_templates()) or 'none'}")


@cache
def load_python_template(path: Path) -> Template:
    """The `TEMPLATE` a Python template file defines (an instance, or a class to instantiate).
    Each file is run once; it may import rmstrokes and find its own assets next to __file__."""
    digest = hashlib.sha1(str(path).encode()).hexdigest()[:10]
    spec = importlib.util.spec_from_file_location(f"rmstrokes_template_{path.stem}_{digest}", path)
    if spec is None or spec.loader is None:
        raise SchemaError(f"template file {path} can't be loaded as Python")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module  # dataclasses and pickling look the module up by name
    try:
        spec.loader.exec_module(module)
    except BaseException:
        del sys.modules[spec.name]
        raise
    obj = getattr(module, "TEMPLATE", None)
    template = obj() if isinstance(obj, type) and issubclass(obj, Template) else obj
    if not isinstance(template, Template):
        raise SchemaError(f"{path.name}: a Python template file must define TEMPLATE, an rmstrokes.Template")
    return template
