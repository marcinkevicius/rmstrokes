"""Device presets, .rmdoc packaging and the .rm page writer."""
import pytest

from rmstrokes.devices import DEVICES, device_key, get_device
from rmstrokes.rm import page_centre_x, read_layers, rm_page
from rmstrokes.rmdoc import RmdocIds, page_index_keys, read_rmdoc, write_rmdoc
from rmstrokes.vectorize import Stroke


def test_presets_and_verification():
    assert set(DEVICES) == {"rm2", "pro", "move"}
    assert DEVICES["rm2"].verified  # the only tablet checked on hardware
    assert not DEVICES["pro"].verified and not DEVICES["move"].verified
    assert device_key("Paper-Pro") == "pro" and device_key("remarkable2") == "rm2"
    assert get_device(DEVICES["move"]) is DEVICES["move"]
    with pytest.raises(ValueError, match="unknown device"):
        device_key("kindle")
    rm2 = DEVICES["rm2"]
    assert rm2.page_size_pt == pytest.approx((1404 * 72 / 226, 1872 * 72 / 226))
    assert rm2.mm(25.4) == pytest.approx(226)


def test_page_keys_sort_in_page_order():
    keys = page_index_keys(700)
    assert keys == sorted(keys) and len(set(keys)) == 700
    assert page_index_keys(3) == ["ba", "bb", "bc"]


def test_deterministic_ids_depend_on_namespace():
    a, b = RmdocIds.deterministic(2, "s"), RmdocIds.deterministic(2, "s")
    assert a == b
    assert RmdocIds.deterministic(2, "s", "other") != a
    assert RmdocIds.random(2) != RmdocIds.random(2)


def test_rm_page_layers_and_coordinates():
    dev = DEVICES["rm2"]
    s = Stroke(((100.0, 50.0), (110.0, 60.0)), 3.0)
    ids = RmdocIds.random(1)
    rm = rm_page([("Notes", []), ("Things", [s])], dev, ids.author)
    (n0, l0), (n1, l1) = read_layers(rm)
    assert (n0, len(l0), n1, len(l1)) == ("Notes", 0, "Things", 1)
    assert l1[0].points[0].x == pytest.approx(100 - dev.width / 2) and l1[0].points[0].y == 50
    land = read_layers(rm_page([("Things", [s])], dev, ids.author, landscape=True))
    assert land[0][1][0].points[0].x == pytest.approx(100 - dev.height / 2)
    assert page_centre_x(dev, True) == dev.height / 2
    with pytest.raises(ValueError, match="at least one layer"):
        rm_page([], dev, ids.author)


def test_write_and_read_rmdoc(tmp_path):
    ids = RmdocIds.deterministic(2, "t")
    dev = DEVICES["pro"]
    pages = [rm_page([("L", [])], dev, ids.author) for _ in range(2)]
    path = write_rmdoc(tmp_path / "x.rmdoc", "Name", b"%PDF-1.4", pages, ids, now_ms=5,
                       orientation="landscape")
    doc = read_rmdoc(path)
    assert doc.metadata["visibleName"] == "Name" and doc.metadata["createdTime"] == "5"
    assert doc.content["orientation"] == "landscape" and doc.content["pageCount"] == 2
    assert [pid for pid, _ in doc.pages] == list(ids.pages)
    assert doc.content["cPages"]["uuids"][0]["first"] == str(ids.author)
    with pytest.raises(ValueError):
        write_rmdoc(tmp_path / "y.rmdoc", "N", b"", pages[:1], ids)
