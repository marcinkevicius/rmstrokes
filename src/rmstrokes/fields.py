"""Write-in fields on the background: a label and a ruled line, a box, or a few ruled lines.

    Today I will ______________ first        (WriteIn("Today I will", after="first"))

Fields are printed in the PDF; whatever is written on them is ordinary handwriting.
"""
from __future__ import annotations

from dataclasses import dataclass

from reportlab.pdfbase import pdfmetrics

from . import design, fonts
from .geometry import Rect
from .pdf import Painter

KINDS = ("line", "box", "lines")


@dataclass(frozen=True)
class FieldStyle:
    label_font: str = design.SANS_ITALIC
    text_font: str = design.SANS
    size_mm: float = 3.6
    label_color: str = "#000000"
    rule_color: str = "#6E6E6E"
    rule_width_mm: float = 0.25
    value_color: str = "#000000"
    pitch_mm: float = 8.0   # line spacing for "lines"

    @classmethod
    def from_style(cls, style, size_mm: float | None = None) -> "FieldStyle":
        """Fonts, colours and weights from a design.Style: the label in the `field` role, a
        pre-filled value in `value`, the line in `rule` grey at the rule weight."""
        label = style.type("field")
        return cls(label_font=label.font, text_font=style.font("value"),
                   size_mm=label.size_mm if size_mm is None else size_mm,
                   label_color=style.color(label.color), rule_color=style.color("rule"),
                   rule_width_mm=style.lines.rule,
                   value_color=style.color("ink"), pitch_mm=style.spacing.write_pitch)


@dataclass(frozen=True)
class WriteIn:
    label: str = ""   # text before the blank (above a box)
    after: str = ""   # text after the blank, on the same line ("line" only)
    kind: str = "line"
    value: str = ""   # pre-filled text

    def __post_init__(self):
        if self.kind not in KINDS:
            raise ValueError(f"write-in kind must be one of {', '.join(KINDS)}, not {self.kind!r}")


def draw_line_field(p: Painter, label: str, value: str, x0: float, x1: float, baseline: float,
                    size: float, *, label_font: str, text_font: str, label_color: str,
                    rule_color: str, rule_width: float, value_color: str, after: str = ""):
    """A label followed by a hairline rule to write on (and a pre-filled value, if any); `after`
    is set at the right end, the rule stopping short of it."""
    gap = p.mm(1.2)
    p.text(label, x0, baseline, label_font, size, label_color)
    start = x0 + (pdfmetrics.stringWidth(label, label_font, size) + gap if label else 0)
    end = x1
    if after:
        fonts.font(label_font)
        end = x1 - pdfmetrics.stringWidth(after, label_font, size) - gap
        p.text(after, x1, baseline, label_font, size, label_color, "right")
    rule_y = baseline + p.mm(0.7)
    p.line(start, rule_y, end, rule_y, rule_width, rule_color)
    if value:
        p.text(value, start + gap, baseline, text_font, size * 1.15, value_color)


def draw_write_in(p: Painter, field: WriteIn, rect: Rect, style: FieldStyle = FieldStyle()):
    """`field` in `rect`: for "line" the baseline sits near the rect's bottom; a "box" has its
    label above the frame; "lines" fills the rect with ruled lines under the label."""
    size = p.mm(style.size_mm)
    fonts.font(style.label_font)
    kw = dict(label_font=style.label_font, text_font=style.text_font, label_color=style.label_color,
              rule_color=style.rule_color, rule_width=p.mm(style.rule_width_mm),
              value_color=style.value_color)
    if field.kind == "line":
        draw_line_field(p, field.label, field.value, rect.x, rect.right, rect.bottom - p.mm(1.2),
                        size, after=field.after, **kw)
        return
    top = rect.y
    if field.label:
        p.text(field.label, rect.x, rect.y + size, style.label_font, size, style.label_color)
        top = rect.y + size + p.mm(1.5)
    if field.kind == "box":
        p.rect(Rect(rect.x, top, rect.w, rect.bottom - top), stroke=style.rule_color,
               width=p.mm(style.rule_width_mm), radius=p.mm(1.5))
        if field.value:
            p.text(field.value, rect.x + p.mm(2), top + size * 1.6, style.text_font, size * 1.15,
                   style.value_color)
        return
    pitch = p.mm(style.pitch_mm)
    y = top + pitch
    while y <= rect.bottom + 1e-6:
        p.line(rect.x, y, rect.right, y, p.mm(style.rule_width_mm), style.rule_color)
        y += pitch
