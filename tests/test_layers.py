"""The layer API: pages with a background and named stroke layers, written as .rmdoc or PDF."""
import pytest

from rmstrokes.devices import DEVICES
from rmstrokes.layers import Document, Layer, Page
from rmstrokes.rm import read_layers
from rmstrokes.rmdoc import read_rmdoc
from rmstrokes.vectorize import Stroke
from strokes_helpers import layers, pdf_page_count, pdf_text

DOT = Stroke(((200.0, 200.0), (260.0, 200.0)), 4.0)


def background(text):
    def draw(p):
        p.text(text, p.mm(10), p.mm(20), "AtkinsonHyperlegibleNext-Regular", p.mm(5), "#000000")
    return draw


def test_handwriting_layer_and_active_layer():
    page = Page(background("x"), [Layer("A", [DOT]), Layer("B", [DOT, DOT])], handwriting="Notes")
    assert [n for n, _ in page.rm_layers()] == ["Notes", "A", "B"]
    assert page.active_index() == 2  # the top stroke layer
    top = Page(None, [Layer("A")], handwriting="Notes", handwriting_on_top=True, active="Notes")
    assert [n for n, _ in top.rm_layers()] == ["A", "Notes"] and top.active_index() == 1
    assert Page(None, handwriting="Only").rm_layers() == [("Only", [])]
    with pytest.raises(ValueError, match="at least one layer"):
        Page(None).rm_layers()
    with pytest.raises(ValueError, match="repeat"):
        Page(None, [Layer("A"), Layer("A")]).rm_layers()
    with pytest.raises(ValueError, match="not one of"):
        Page(None, [Layer("A")], active="Z").active_index()


def test_any_number_of_layers_round_trip(tmp_path):
    dev = DEVICES["rm2"]
    pages = [Page(background(f"page {i}"), [Layer(f"L{j}", [DOT] * j) for j in range(1, 4)], handwriting="Writing")
             for i in range(2)]
    result = Document(dev, pages, title="Layers").write(tmp_path / "l.rmdoc", seed="s")
    assert layers(result.path) == [[("Writing", 0), ("L1", 1), ("L2", 2), ("L3", 3)]] * 2
    doc = read_rmdoc(result.path)
    assert pdf_page_count(doc.pdf) == 2 and "page 1" in pdf_text(doc.pdf, 1)
    assert doc.metadata["visibleName"] == "Layers"
    # Reproducible with a seed.
    again = Document(dev, pages, title="Layers").write(tmp_path / "m.rmdoc", seed="s")
    assert again.rm == result.rm


def test_pdf_prints_the_strokes_and_rmdoc_does_not(tmp_path):
    import pypdfium2 as pdfium

    dev = DEVICES["rm2"]
    doc = Document(dev, [Page(None, [Layer("A", [Stroke(((100.0, 100.0), (600.0, 100.0)), 20.0)])])])

    def ink(pdf):
        page = pdfium.PdfDocument(pdf)[0]
        img = page.render(scale=dev.dpi / 72).to_pil().convert("L")
        return img.getpixel((350, 100))

    assert ink(doc.render_pdf(print_strokes=True)) < 50
    assert ink(doc.render_pdf()) > 200
    assert doc.write(tmp_path / "a.pdf").format == "pdf"
    with pytest.raises(ValueError, match="format"):
        doc.write(tmp_path / "a.x", "svg")


def test_landscape_document(tmp_path):
    dev = DEVICES["rm2"]
    doc = Document(dev, [Page(None, [Layer("A", [DOT])], landscape=True)])
    r = doc.write_rmdoc(tmp_path / "l.rmdoc")
    rd = read_rmdoc(r.path)
    assert rd.content["orientation"] == "landscape"
    (_, lines), = read_layers(rd.pages[0][1])
    assert lines[0].points[0].x == pytest.approx(200 - dev.height / 2)
    import io

    from pypdf import PdfReader
    box = PdfReader(io.BytesIO(rd.pdf)).pages[0].mediabox
    assert float(box.width) > float(box.height)


def test_one_orientation_per_document():
    dev = DEVICES["rm2"]
    doc = Document(dev, [Page(None, [Layer("A")], kind="chart"), Page(None, [Layer("A")], landscape=True, kind="sheet")])
    with pytest.raises(ValueError, match=r"page 2 is sheet \(landscape\) but page 1 is chart \(portrait\)"):
        doc.render_pdf()
