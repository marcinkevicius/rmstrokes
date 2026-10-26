"""Repository hygiene: no file about to be committed holds a local path, is a generated document or
a secret, or matches one of your own patterns.

Scans what git would commit (tracked files plus untracked, not ignored ones), so a new file fails
before it is committed. Your own patterns (your user name or machine name, say) go one
regular expression per line in `info/commit-patterns` in the git directory: git never commits or
pushes that file, and every worktree of the clone shares it."""
import re
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]

PATHS = r"/Users/|/home/"
BINARY_SUFFIXES = {".png", ".pdf", ".ttf", ".svg"}
# The OFL texts are upstream's legal wording; uv.lock is full of PyPI URLs; this file names the patterns.
SKIP_TEXT = {"uv.lock", "tests/test_repo_hygiene.py"}


def _git(*args: str) -> str:
    if shutil.which("git") is None:
        pytest.skip("git isn't installed")
    r = subprocess.run(["git", *args], cwd=ROOT, capture_output=True)
    if r.returncode:
        pytest.skip("not a git checkout")
    return r.stdout.decode()


def _patterns() -> tuple[re.Pattern, re.Pattern]:
    """For binary files, and for text files and names (which also get `text:` patterns, words that
    turn up in PDFs by chance)."""
    own = Path(_git("rev-parse", "--path-format=absolute", "--git-common-dir").strip()) / "info" / "commit-patterns"
    lines = own.read_text().splitlines() if own.exists() else []
    extra = [ln.strip() for ln in lines if ln.strip() and not ln.lstrip().startswith("#")]
    text_only = [ln[len("text:"):] for ln in extra if ln.startswith("text:")]
    both = "|".join([PATHS, *(ln for ln in extra if not ln.startswith("text:"))])
    return re.compile(both, re.I), re.compile("|".join([both, *text_only]), re.I)


def _files() -> list[str]:
    out = _git("ls-files", "-z", "--cached", "--others", "--exclude-standard")
    return sorted(f for f in out.split("\0") if f and (ROOT / f).is_file())


def _strings(data: bytes) -> list[bytes]:
    """Printable ASCII runs of four or more characters, like `strings -a`."""
    return re.findall(rb"[\x20-\x7e]{4,}", data)


def test_no_local_paths_or_own_patterns():
    binary_re, text_re = _patterns()
    hits = []
    for f in _files():
        if text_re.search(f):
            hits.append(f"{f}: file name")
        path = ROOT / f
        if path.suffix.lower() in BINARY_SUFFIXES:
            for run in _strings(path.read_bytes()):
                if m := binary_re.search(run.decode("ascii")):
                    hits.append(f"{f}: {m.group(0)!r} in binary data")
            if path.suffix.lower() != ".svg":
                continue
        if f in SKIP_TEXT or Path(f).name.startswith("OFL-"):
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        for n, line in enumerate(text.splitlines(), 1):
            if m := text_re.search(line):
                hits.append(f"{f}:{n}: {m.group(0)!r}")
    assert not hits, "found (fix the files, don't loosen the check):\n" + "\n".join(hits)


def test_no_generated_documents_or_secrets():
    bad = []
    for f in _files():
        p = Path(f)
        if p.suffix in {".rmdoc", ".zip", ".pdf"} or (p.name.startswith(".env") and p.name != ".env.example"):
            bad.append(f)
    assert not bad, "generated documents or secrets :\n" + "\n".join(bad)
