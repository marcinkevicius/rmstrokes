"""rmstrokes: build reMarkable documents (PDF background + movable pen strokes) from templates.

  rmstrokes build recipe.toml -o out.rmdoc     # one document from a recipe (mixed page types)
  rmstrokes build recipe.toml --device all -o out/
  rmstrokes make gaps --words sun --words rain --intro -o gaps.rmdoc   # one template, flags from its schema
  rmstrokes make my-template.toml -o mine.pdf  # a template file of your own
  rmstrokes templates                          # what can be built
  rmstrokes params gaps                        # a template's parameters (markdown; --recipe: TOML)
  rmstrokes params --all                       # every template's parameters
  rmstrokes devices
  rmstrokes specimen -o out/                   # the design system's tokens: rm2 (default) and pro (color)
  rmstrokes gallery                            # every template and example, for review (gallery.toml)
  rmstrokes explain gaps -o explain/           # how a page is built, step by step: a PNG per step
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path
from typing import Sequence

from . import __version__
from .design import THEMES
from .devices import ALIASES, DEVICES
from .params import SchemaError
from .recipe import build_recipe, load_recipe
from .run import add_output_arguments, output_format, output_path, template_main
from .templates import COMMON_NAMES, Template, available_templates, common_schema, device_arg, get_template


def cmd_build(args) -> int:
    devices = list(DEVICES) if args.device == "all" else [args.device]
    fmt = output_format(args.out, args.format)
    if len(devices) > 1 and args.out and args.out.suffix:
        raise ValueError("--device all writes one file per device: give -o a folder")
    for key in devices:
        recipe = load_recipe(args.recipe, device=key if args.device else None,
                             allow_python=getattr(args, "allow_python", False))
        doc = build_recipe(recipe)
        out = output_path(args.out, f"{recipe.stem}-{recipe.device}.{fmt}", len(devices) > 1)
        if recipe.name is None:
            doc.title = out.stem
        result = doc.write(out, fmt)
        kinds = ", ".join(dict.fromkeys(p.kind or "page" for p in doc.pages))
        print(f"{result.path}: {doc.device.name}, {len(doc.pages)} page(s) ({kinds}), "
              f"{result.size_kib():.1f} KiB")
    return 0


def add_build_arguments(parser: argparse.ArgumentParser):
    """`build RECIPE [--device D] [--allow-python] [-o OUT] [--format F]`; other tools can reuse it for their
    own build command."""
    parser.add_argument("recipe", type=Path, help="recipe file (.toml or .json)")
    parser.add_argument("--device", type=device_arg, default=None, metavar="DEVICE",
                        help="override the recipe's device; all = one file per device")
    parser.add_argument("--allow-python", action="store_true",
                        help="let the recipe use Python template files (.py); they run as code, so only for "
                             "files you trust")
    add_output_arguments(parser, default_stem="<recipe>")
    parser.set_defaults(func=cmd_build)


def cmd_templates(args) -> int:
    for name, where in available_templates().items():
        try:
            t = get_template(name)
            print(f"  {name}\t{t.title}: {t.description}\n  \t{where}")
        except Exception as e:  # a broken installed template shouldn't hide the others
            print(f"  {name}\t(can't load: {e})\n  \t{where}")
    return 0


def parameters_markdown() -> str:
    """The parameter reference of every available template, generated from their schemas.
    Theme names aren't listed: they can come from external asset folders."""
    common = common_schema(Template())
    parts = ["## Common to every template\n\nThe theme's default and choices are the template's own.\n\n"
             + common.markdown()]
    for name in available_templates():
        t = get_template(name)
        parts.append(f"## {t.title} (`{t.name}`)\n\n{t.description}\n\nDefault theme: `{t.default_theme}`."
                     f"\n\n{t.params.markdown()}")
    return "\n\n".join(parts) + "\n"


def cmd_params(args) -> int:
    if args.all:
        print(parameters_markdown(), end="")
        return 0
    if not args.template:
        raise ValueError("name a template, or --all")
    t = get_template(args.template)
    if args.recipe:
        print(f'[[pages]]\ntemplate = "{t.name}"\n# common: theme, copies\n'
              + "\n".join(line for line in t.schema.recipe_example().splitlines()
                          if line.split()[0].lstrip("#") not in COMMON_NAMES
                          and not line.startswith("# device")))
    else:
        print(f"## {t.title} (`{t.name}`)\n\n{t.description}\n\n{t.schema.markdown()}")
    return 0


def cmd_devices(args) -> int:
    for key, d in DEVICES.items():
        aliases = ", ".join(a for a, k in ALIASES.items() if k == key)
        note = "" if d.verified else "  [unverified: not yet checked on a real tablet]"
        print(f"  {key}\t{d.name}, {d.width}x{d.height} px @ {d.dpi} ppi (also: {aliases}){note}")
    return 0


def cmd_specimen(args) -> int:
    from .specimen import DEFAULT_RUNS, write_specimens
    if args.device is None and args.theme is None:
        runs = list(DEFAULT_RUNS)
    else:
        devices = (list(DEVICES) if args.device == "all" else [args.device]) if args.device else ["rm2", "pro"]
        themes = list(THEMES) if args.theme == "all" else [args.theme] if args.theme else None
        runs = [(d, t) for d in devices
                for t in (themes or ["color" if DEVICES[d].color else "default"])]
    for path in write_specimens(args.out, runs, png=not args.no_png):
        print(path)
    unverified = sorted({DEVICES[d].name for d, _ in runs if not DEVICES[d].verified})
    if unverified:
        print(f"note: {', '.join(unverified)}: unverified, not yet checked on a real tablet")
    return 0


def cmd_gallery(args) -> int:
    from . import gallery
    g = gallery.load_gallery(args.config, with_move=args.with_move, only=args.only)
    if args.dry_run:
        print("\n".join(gallery.describe(g)))
        print(f"{len(g.jobs)} document(s): {len(g.jobs) // len(g.devices)} on each of "
              f"{', '.join(d.key for d in g.devices)}; nothing written (--dry-run)")
        return 0
    out = args.out.expanduser() if args.out else gallery.default_out(g.config)
    results = gallery.run_gallery(g, out)
    failed = [b for b in results if b.error]
    explained = [x for x in g.explained if x.error]
    print(f"{out / 'index.html'}: {len(results) - len(failed)} document(s)"
          f"{f', {len(failed)} FAILED' if failed else ''}"
          f"{f', {len(explained)} explainer(s) FAILED' if explained else ''}")
    return 1 if failed or explained else 0


def explain_command(args) -> str:
    """The command line that makes this markdown page, as typed (for the page's header)."""
    device = f" --device {args.device}" if args.device != "rm2" else ""
    return (f"rmstrokes explain {' '.join(args.templates)}{device} -o {args.out.as_posix()} "
            f"--markdown {args.markdown.as_posix()}")


def cmd_explain(args) -> int:
    from .explain import explain, markdown, write_explainers
    devices = list(DEVICES) if args.device == "all" else [args.device]
    explainers = [explain(t, d) for t in args.templates for d in devices]
    for path in write_explainers(explainers, args.out, documents=not args.no_documents):
        print(path)
    if args.markdown:
        image_dir = Path(os.path.relpath(args.out.resolve(), args.markdown.resolve().parent)).as_posix()
        args.markdown.parent.mkdir(parents=True, exist_ok=True)
        args.markdown.write_text(markdown(explainers, "" if image_dir == "." else image_dir,
                                          explain_command(args)), encoding="utf-8")
        print(args.markdown)
    unverified = sorted({DEVICES[d].name for d in devices if not DEVICES[d].verified})
    if unverified:
        print(f"note: {', '.join(unverified)}: unverified, not yet checked on a real tablet")
    return 0


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(prog="rmstrokes", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--version", action="version", version=f"rmstrokes {__version__}")
    sub = ap.add_subparsers(dest="command", metavar="COMMAND", required=True)
    add_build_arguments(sub.add_parser("build", help="one document from a recipe file (TOML or JSON)"))
    sub.add_parser("make", help="one template, its parameters as flags: rmstrokes make NAME --help")
    t = sub.add_parser("templates", help="list the templates")
    t.set_defaults(func=cmd_templates)
    p = sub.add_parser("params", help="a template's parameters (markdown table, or --recipe)")
    p.add_argument("template", nargs="?")
    p.add_argument("--recipe", action="store_true", help="as a [[pages]] section with the defaults")
    p.add_argument("--all", action="store_true", help="every template's parameters (the docs reference)")
    p.set_defaults(func=cmd_params)
    d = sub.add_parser("devices", help="list the device presets")
    d.set_defaults(func=cmd_devices)
    sp = sub.add_parser("specimen", help="the design system's specimen page: rmdoc, PDF and PNG per device")
    sp.add_argument("--device", type=device_arg, default=None, metavar="DEVICE",
                    help="one device, or all (default: rm2 and pro)")
    sp.add_argument("--theme", choices=(*THEMES, "all"), default=None,
                    help="design theme (default: color on the colour devices, default on the rm2)")
    sp.add_argument("-o", "--out", type=Path, default=Path("specimen"), help="output folder (default: ./specimen)")
    sp.add_argument("--no-png", action="store_true", help="skip the PNG previews (they need pypdfium2)")
    sp.set_defaults(func=cmd_specimen)
    g = sub.add_parser("gallery", help="every template and example, rm2 and Paper Pro, with a contact sheet",
                       description="Build every template (its defaults, with the intro page) and every "
                                   "example of the gallery config, as .rmdoc, .pdf and a PNG of the first "
                                   "page, with an index.html contact sheet.")
    g.add_argument("config", nargs="?", type=Path, default=Path("gallery.toml"),
                   help="gallery config (default: ./gallery.toml)")
    g.add_argument("-o", "--out", type=Path,
                   help="a new or empty folder (default: ~/rmstrokes-gallery/<date>-<time>-<commit>/)")
    g.add_argument("--with-move", action="store_true", help="also the Paper Pro Move")
    g.add_argument("--only", action="append", metavar="GROUP", help="only this group's documents; repeatable")
    g.add_argument("--dry-run", action="store_true", help="list and check what would be built, write nothing")
    g.set_defaults(func=cmd_gallery)
    e = sub.add_parser("explain", help="how a page is built, step by step: a PNG per step, and the page itself",
                       description="Draw how a template's first page is built, in five pictures: what goes in "
                                   "(parameter text, token shapes and SVGs), the layout, one token becoming pen "
                                   "strokes, the layers, and the finished page (.rmdoc and PDF). Writes "
                                   "<template>-<device>-<n>-<step>.png and the page as .rmdoc and .pdf.")
    e.add_argument("templates", nargs="*", default=["gaps"], metavar="TEMPLATE",
                   help="template names or .toml/.py files (default: gaps)")
    e.add_argument("--device", type=device_arg, default="rm2", metavar="DEVICE",
                   help="one device, or all (default: rm2)")
    e.add_argument("-o", "--out", type=Path, default=Path("explain"), help="output folder (default: ./explain)")
    e.add_argument("--markdown", type=Path, metavar="FILE",
                   help="also write the steps as a markdown page, linking the PNGs")
    e.add_argument("--no-documents", action="store_true", help="only the pictures, not the .rmdoc and .pdf")
    e.set_defaults(func=cmd_explain)
    return ap


def main(argv: Sequence[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else list(argv)
    if argv[:1] == ["make"]:
        if len(argv) < 2 or argv[1].startswith("-"):
            print("usage: rmstrokes make TEMPLATE [--help | parameters]", file=sys.stderr)
            return 2
        try:
            template = get_template(argv[1])
        except SchemaError as e:
            print(f"rmstrokes: {e}", file=sys.stderr)
            return 2
        return template_main(template, argv[2:], prog=f"rmstrokes make {argv[1]}")
    args = build_parser().parse_args(argv)
    try:
        return args.func(args)
    except (ValueError, OSError) as e:
        print(f"rmstrokes: {e}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
