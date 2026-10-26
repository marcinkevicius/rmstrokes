"""The command line for one template, generated from its schema.

    template_main(MY_TEMPLATE, argv, prog="mytool")

gives `mytool [--device D] [--theme T] [--name N] [--copies N] [--intro] [template flags]
[-o OUT] [--format rmdoc|pdf]`, writes one document per device and prints a summary line per
file. Other tools can embed the same arguments in their own subcommands (add_template_arguments +
run_template).
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Callable, Sequence

from .devices import DEVICES, get_device
from .layers import FORMATS
from .recipe import Section, build_document
from .templates import Template


def output_format(out: Path | None, fmt: str | None) -> str:
    """--format, else the -o extension, else rmdoc."""
    suffix = out.suffix.lower().lstrip(".") if out and out.suffix else ""
    if fmt:
        if suffix in FORMATS and suffix != fmt:
            raise ValueError(f"--format {fmt} but the output file ends in .{suffix}")
        return fmt
    return suffix if suffix in FORMATS else "rmdoc"


def output_path(out: Path | None, stem: str, multi: bool) -> Path:
    """-o as given, or `stem` inside it (a folder, or several files to write), or in the cwd."""
    if out is None:
        return Path(stem)
    if multi or out.is_dir() or not out.suffix:
        return out / stem
    return out


def add_output_arguments(parser: argparse.ArgumentParser, *, default_stem: str = "<name>",
                         format_help: str | None = None):
    parser.add_argument("-o", "--out", type=Path,
                        help=f"output file (.rmdoc or .pdf) or folder (default: ./{default_stem}-<device>.rmdoc)")
    parser.add_argument("--format", choices=FORMATS,
                        help=format_help or "rmdoc: strokes movable on the tablet; pdf: printed, for any "
                                            "reader (default: from the -o extension, else rmdoc)")


def add_template_arguments(parser: argparse.ArgumentParser, template: Template):
    """The common document parameters, the template's own, and the output options."""
    common = template.common()
    for p in common:
        if p.name == "device":
            parser.add_argument("--device", type=p.argtype, default="rm2", metavar="DEVICE",
                                help=f"{p.help} or all (default: rm2)")
        else:
            p.add_argument(parser)
    template.params.add_arguments(parser)
    add_output_arguments(parser, default_stem=template.default_name)


def run_template(template: Template, args: argparse.Namespace) -> int:
    raw = template.schema.from_args(args)
    devices = list(DEVICES) if args.device == "all" else [args.device]
    fmt = output_format(args.out, args.format)
    if len(devices) > 1 and args.out and args.out.suffix:
        raise ValueError("--device all writes one file per device: give -o a folder")
    for key in devices:
        values = template.validate({**raw, "device": key})
        device = get_device(key)
        ctx = template.context(device, values["theme"], values["name"])
        out = output_path(args.out, f"{values['name'] or template.default_name}-{key}.{fmt}", len(devices) > 1)
        doc = build_document([Section(template, values)], device, name=values["name"], intro=values["intro"])
        doc.title = values["name"] or template.default_title or out.stem
        result = doc.write(out, fmt, namespace=template.seed_namespace) if fmt == "rmdoc" else doc.write(out, fmt)
        print(template.summary(result, doc, values, ctx))
        template.written(result, doc, values, ctx)
    return 0


def template_main(template: Template, argv: Sequence[str] | None = None, *, prog: str,
                  description: str | None = None, parents: Sequence[argparse.ArgumentParser] = (),
                  setup: Callable[[argparse.Namespace], None] | None = None,
                  errors: tuple[type[BaseException], ...] = (ValueError, OSError)) -> int:
    ap = argparse.ArgumentParser(prog=prog, description=description or template.description,
                                 parents=list(parents))
    add_template_arguments(ap, template)
    args = ap.parse_args(sys.argv[1:] if argv is None else list(argv))
    try:
        if setup is not None:
            setup(args)
        return run_template(template, args)
    except errors as e:
        print(f"{prog}: {e}", file=sys.stderr)
        return 2
