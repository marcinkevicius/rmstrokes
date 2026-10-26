"""The layer API: a document is pages; each page is one PDF background plus named stroke layers.

    page = Page(draw=my_background,                  # draws the PDF page (a Painter, page px)
                layers=[Layer("Tokens", strokes)],   # pen strokes, bottom to top
                handwriting="Notes")                 # optional empty layer to write on
    Document(get_device("rm2"), [page], title="My sheet").write("sheet.rmdoc")

On the tablet the background is fixed (it is the PDF), the stroke layers are ordinary pen strokes:
select the layer, lasso, drag. Keeping handwriting on a separate, empty layer means a lasso on the
stroke layer never picks it up; write on the stroke layer itself when something written should
move with the strokes (a name in a token's tag, see tokens.py).

`Document.write` gives an .rmdoc (strokes movable) or a plain PDF (strokes printed on the page).
"""
from __future__ import annotations

import io
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Callable, Sequence

from reportlab.pdfgen.canvas import Canvas

from .design import SANS
from .devices import Device
from .fonts import font
from .geometry import page_size
from .pdf import Painter, draw_strokes
from .rm import rm_page
from .rmdoc import RmdocIds, write_rmdoc
from .vectorize import Stroke

FORMATS = ("rmdoc", "pdf")


@dataclass
class Layer:
    name: str
    strokes: list[Stroke] = field(default_factory=list)


@dataclass
class Page:
    """One page: a background drawn into the PDF, plus layers of pen strokes.

    `draw(painter)` is called with the canvas already set up in page px (y down). `handwriting`
    names an empty layer added below the stroke layers (or above them, `handwriting_on_top`).
    `active` is the layer selected when the page opens; by default the top stroke layer.
    """

    draw: Callable[[Painter], None] | None = None
    layers: list[Layer] = field(default_factory=list)
    handwriting: str | None = None
    handwriting_on_top: bool = False
    active: str | None = None
    landscape: bool = False
    fonts: tuple[str, ...] = ()  # registered before drawing (text measuring needs them too)
    kind: str = ""  # what made it ("intro", a template name); for summaries and tests
    meta: dict = field(default_factory=dict, compare=False, repr=False)  # the template's own data

    def rm_layers(self) -> list[tuple[str, list[Stroke]]]:
        """(name, strokes) bottom to top, as the .rm writer takes them."""
        out = [(layer.name, list(layer.strokes)) for layer in self.layers]
        if self.handwriting:
            hw = (self.handwriting, [])
            out = [*out, hw] if self.handwriting_on_top else [hw, *out]
        if not out:
            raise ValueError("a page needs at least one layer (a stroke layer or a handwriting layer)")
        names = [n for n, _ in out]
        if len(set(names)) != len(names):
            raise ValueError(f"layer names repeat on one page: {names}")
        return out

    def active_index(self) -> int:
        names = [n for n, _ in self.rm_layers()]
        if self.active is not None:
            if self.active not in names:
                raise ValueError(f"active layer {self.active!r} is not one of {names}")
            return names.index(self.active)
        if self.layers:
            return names.index(self.layers[-1].name)
        return len(names) - 1

    @property
    def strokes(self) -> list[Stroke]:
        """Every stroke on the page, bottom layer first."""
        return [s for layer in self.layers for s in layer.strokes]

    def layer(self, name: str) -> Layer:
        return next(layer for layer in self.layers if layer.name == name)

    def copy(self) -> Page:
        return replace(self, layers=[Layer(layer.name, list(layer.strokes)) for layer in self.layers])


@dataclass
class Document:
    device: Device
    pages: list[Page]
    title: str = "Untitled"
    creator: str = "rmstrokes"
    subject: str = ""
    fonts: tuple[str, ...] = ()
    initial_font: str = SANS

    @property
    def landscape(self) -> bool:
        """The document's orientation. A reMarkable document has one; mixing is refused."""
        if not self.pages:
            raise ValueError("a document needs at least one page")
        first = self.pages[0].landscape
        odd = [i for i, p in enumerate(self.pages, 1) if p.landscape != first]
        if odd:
            def kind(p):
                return f"{p.kind or 'page'} ({'landscape' if p.landscape else 'portrait'})"
            raise ValueError(f"page {odd[0]} is {kind(self.pages[odd[0] - 1])} but page 1 is "
                             f"{kind(self.pages[0])}; a reMarkable document has one orientation, so "
                             "put landscape and portrait pages in separate documents")
        return first

    @property
    def orientation(self) -> str:
        return "landscape" if self.landscape else "portrait"

    def render_pdf(self, *, print_strokes: bool = False, out: Path | str | None = None) -> bytes:
        """The PDF: every page's background, plus its strokes printed on top with `print_strokes`
        (the PDF-only export). Returns the bytes; also writes `out` if given."""
        landscape = self.landscape
        k = self.device.pt_per_px
        w, h = page_size(self.device, landscape)
        for name in sorted({*self.fonts, self.initial_font, *(f for p in self.pages for f in p.fonts)}):
            font(name)
        buf = io.BytesIO()
        # reportlab selects an initial font on every page; make it a bundled one so the PDF never
        # references an unembedded base-14 font.
        canvas = Canvas(buf, pagesize=(w * k, h * k), invariant=True, pageCompression=1,
                        initialFontName=self.initial_font)
        canvas.setTitle(self.title)
        canvas.setCreator(self.creator)
        canvas.setSubject(self.subject)
        for page in self.pages:
            p = Painter(canvas, self.device, landscape)
            p.begin_page()
            if page.draw is not None:
                page.draw(p)
            if print_strokes:
                draw_strokes(p, page.strokes)
            canvas.showPage()
        canvas.save()
        pdf = buf.getvalue()
        if out is not None:
            out = Path(out)
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_bytes(pdf)
        return pdf

    def rm_pages(self, author) -> list[bytes]:
        landscape = self.landscape
        return [rm_page(p.rm_layers(), self.device, author, active_layer=p.active_index(),
                        landscape=landscape) for p in self.pages]

    def ids(self, seed: str | None = None, namespace: str = "rmstrokes") -> RmdocIds:
        n = len(self.pages)
        return RmdocIds.deterministic(n, seed, namespace) if seed else RmdocIds.random(n)

    def write_rmdoc(self, path: Path | str, *, ids: RmdocIds | None = None, seed: str | None = None,
                    namespace: str = "rmstrokes", now_ms: int | None = None) -> DocumentResult:
        """Write the .rmdoc: the PDF background with the strokes as movable pen strokes."""
        ids = ids or self.ids(seed, namespace)
        pdf = self.render_pdf()
        rms = self.rm_pages(ids.author)
        path = write_rmdoc(Path(path), self.title, pdf, rms, ids, now_ms=now_ms,
                           orientation=self.orientation)
        return DocumentResult(path, "rmdoc", pdf, rms, ids)

    def write_pdf(self, path: Path | str) -> DocumentResult:
        """Write a plain PDF with the strokes printed (any PDF reader; not movable)."""
        pdf = self.render_pdf(print_strokes=True, out=path)
        return DocumentResult(Path(path), "pdf", pdf, [], None)

    def write(self, path: Path | str, fmt: str | None = None, **kw) -> DocumentResult:
        path = Path(path)
        fmt = fmt or ("pdf" if path.suffix.lower() == ".pdf" else "rmdoc")
        if fmt not in FORMATS:
            raise ValueError(f"format must be one of {', '.join(FORMATS)}, not {fmt!r}")
        return self.write_pdf(path) if fmt == "pdf" else self.write_rmdoc(path, **kw)


@dataclass
class DocumentResult:
    path: Path
    format: str
    pdf: bytes
    rm: list[bytes]  # one per page (empty for a PDF)
    ids: RmdocIds | None

    def size_kib(self) -> float:
        return self.path.stat().st_size / 1024


def stroke_count(pages: Sequence[Page]) -> int:
    return sum(len(p.strokes) for p in pages)
