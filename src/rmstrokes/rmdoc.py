"""`.rmdoc` packaging: a zip of .content, .metadata, the PDF and one .rm per page.
See docs/format-notes.md sections 1 and 3."""
from __future__ import annotations

import json
import time
import uuid
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence


def page_index_keys(n: int) -> list[str]:
    """Fractional sort keys in device style: 'ba', 'bb', ... 'bz', 'ca', ... (sorted order)."""
    letters = "abcdefghijklmnopqrstuvwxyz"
    keys = []
    width = 2
    while len(keys) < n:
        keys = []
        cap = 25 * 26 ** (width - 1)  # first letter b..z
        for i in range(min(n, cap)):
            digits = []
            v = i
            for _ in range(width - 1):
                digits.append(letters[v % 26])
                v //= 26
            keys.append(letters[1 + v] + "".join(reversed(digits)))
        width += 1
    return keys


@dataclass(frozen=True)
class RmdocIds:
    doc: str
    pages: tuple[str, ...]
    author: uuid.UUID

    @classmethod
    def random(cls, n_pages: int) -> RmdocIds:
        return cls(str(uuid.uuid4()), tuple(str(uuid.uuid4()) for _ in range(n_pages)), uuid.uuid4())

    @classmethod
    def deterministic(cls, n_pages: int, seed: str, namespace: str = "rmstrokes") -> RmdocIds:
        """Reproducible ids: the same (namespace, seed) always gives the same UUIDs."""
        ns = uuid.uuid5(uuid.NAMESPACE_URL, f"{namespace}:{seed}")
        return cls(str(uuid.uuid5(ns, "doc")),
                   tuple(str(uuid.uuid5(ns, f"page{i}")) for i in range(n_pages)),
                   uuid.uuid5(ns, "author"))


def content_json(ids: RmdocIds, pdf_pages: int, size_in_bytes: int,
                 orientation: str = "portrait") -> dict:
    keys = page_index_keys(len(ids.pages))
    pages = [{"id": pid, "idx": {"timestamp": "1:2", "value": key},
              "redir": {"timestamp": "1:2", "value": i}}  # -> PDF page i
             for i, (pid, key) in enumerate(zip(ids.pages, keys))]
    return {
        "cPages": {
            "lastOpened": {"timestamp": "1:1", "value": ids.pages[0]},
            "original": {"timestamp": "1:1", "value": pdf_pages},
            "pages": pages,
            "uuids": [{"first": str(ids.author), "second": 1}],
        },
        "coverPageNumber": 0,
        "documentMetadata": {},
        "extraMetadata": {},
        "fileType": "pdf",
        "fontName": "",
        "formatVersion": 2,
        "lineHeight": -1,
        "orientation": orientation,
        "pageCount": len(ids.pages),
        "pageTags": [],
        "sizeInBytes": str(size_in_bytes),
        "tags": [],
        "textAlignment": "justify",
        "textScale": 1,
        "zoomMode": "bestFit",
    }


def metadata_json(name: str, now_ms: int) -> dict:
    now = str(now_ms)
    return {
        "createdTime": now,
        "lastModified": now,
        "lastOpened": now,
        "lastOpenedPage": 0,
        "parent": "",
        "pinned": False,
        "type": "DocumentType",
        "visibleName": name,
    }


def write_rmdoc(path: Path, name: str, pdf: bytes, pages_rm: Sequence[bytes], ids: RmdocIds,
                *, now_ms: int | None = None, orientation: str = "portrait") -> Path:
    if len(ids.pages) != len(pages_rm):
        raise ValueError("one page id per .rm page")
    now_ms = int(time.time() * 1000) if now_ms is None else now_ms
    size = len(pdf) + sum(map(len, pages_rm))
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr(f"{ids.doc}.content", json.dumps(content_json(ids, len(pages_rm), size, orientation), indent=4))
        z.writestr(f"{ids.doc}.metadata", json.dumps(metadata_json(name, now_ms), indent=4))
        z.writestr(f"{ids.doc}.pdf", pdf)
        for pid, rm in zip(ids.pages, pages_rm):
            z.writestr(f"{ids.doc}/{pid}.rm", rm)
    return path


@dataclass
class RmdocContents:
    """An unpacked .rmdoc (ours or one exported from a device)."""
    doc_id: str
    content: dict
    metadata: dict
    pdf: bytes | None
    pages: list[tuple[str, bytes | None]]  # (page id, .rm bytes or None) in page order
    other_files: list[str]


def read_rmdoc(path: Path) -> RmdocContents:
    with zipfile.ZipFile(path) as z:
        names = z.namelist()
        content_name = next((n for n in names if n.endswith(".content") and "/" not in n), None)
        if content_name is None:
            raise ValueError(f"{path}: no top-level .content file")
        doc_id = content_name[: -len(".content")]
        content = json.loads(z.read(content_name))
        meta_name = f"{doc_id}.metadata"
        metadata = json.loads(z.read(meta_name)) if meta_name in names else {}
        pdf = z.read(f"{doc_id}.pdf") if f"{doc_id}.pdf" in names else None
        page_ids = [p["id"] for p in content.get("cPages", {}).get("pages", [])
                    if not p.get("deleted", {}).get("value")]
        if not page_ids:
            page_ids = list(content.get("pages", []))
        idx = {p["id"]: p.get("idx", {}).get("value", "") for p in content.get("cPages", {}).get("pages", [])}
        page_ids.sort(key=lambda pid: idx.get(pid, ""))
        pages = []
        for pid in page_ids:
            n = f"{doc_id}/{pid}.rm"
            pages.append((pid, z.read(n) if n in names else None))
        used = {content_name, meta_name, f"{doc_id}.pdf", *(f"{doc_id}/{pid}.rm" for pid in page_ids)}
        other = sorted(n for n in names if n not in used and not n.endswith("/"))
    return RmdocContents(doc_id, content, metadata, pdf, pages, other)
