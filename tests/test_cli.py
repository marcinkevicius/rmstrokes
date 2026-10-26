"""The rmstrokes command line."""
from rmstrokes.cli import main
from rmstrokes.rmdoc import read_rmdoc
from strokes_helpers import pdf_page_count


def test_build_a_recipe(tmp_path, capsys):
    (tmp_path / "r.toml").write_text('name = "Plan"\nintro = true\n[[pages]]\ntemplate = "gaps"\ncopies = 2\n')
    assert main(["build", str(tmp_path / "r.toml"), "-o", str(tmp_path / "out.rmdoc")]) == 0
    assert "3 page(s) (intro, gaps)" in capsys.readouterr().out
    assert len(read_rmdoc(tmp_path / "out.rmdoc").pages) == 3
    assert main(["build", str(tmp_path / "r.toml"), "--device", "all", "-o", str(tmp_path / "all")]) == 0
    assert sorted(p.name for p in (tmp_path / "all").iterdir()) == ["Plan-move.rmdoc", "Plan-pro.rmdoc",
                                                                    "Plan-rm2.rmdoc"]


def test_make_one_template_with_flags_from_its_schema(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    assert main(["make", "gaps", "--words", "sun", "--words", "rain", "--copies", "2", "--intro", "-o", "w.pdf"]) == 0
    from pypdf import PdfReader
    assert len(PdfReader("w.pdf").pages) == 3
    assert main(["make", "gaps"]) == 0
    assert (tmp_path / "gaps-rm2.rmdoc").is_file()
    assert main(["make", "gaps", "--copies", "0"]) == 2
    assert "gaps: copies: must be at least 1 (got 0)" in capsys.readouterr().err
    assert main(["make", "nope"]) == 2
    assert pdf_page_count((tmp_path / "w.pdf").read_bytes()) == 3


def test_listing_and_docs(capsys):
    assert main(["templates"]) == 0
    assert "gaps" in capsys.readouterr().out
    assert main(["devices"]) == 0
    lines = {line.split()[0]: line for line in capsys.readouterr().out.splitlines()}
    assert "unverified" not in lines["rm2"] and "unverified" in lines["pro"] and "unverified" in lines["move"]
    assert main(["params", "gaps"]) == 0
    assert "| `words` | `--words` |" in capsys.readouterr().out
    assert main(["params", "gaps", "--recipe"]) == 0
    out = capsys.readouterr().out
    assert 'template = "gaps"' in out and 'words = ["clouds", "rain", "sun", "vapour"]' in out and "device" not in out


def test_errors_exit_2(tmp_path, capsys):
    (tmp_path / "bad.toml").write_text('[[pages]]\ntemplate = "gaps"\ntitle = 1\n')
    assert main(["build", str(tmp_path / "bad.toml")]) == 2
    assert capsys.readouterr().err.startswith("rmstrokes: bad.toml: pages[1] (gaps): title")
