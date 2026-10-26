"""v6 .rm page writer. Block layout modelled on rmscene's device fixtures
(Normal_A_stroke_2_layers_*.rm); see docs/format-notes.md section 2.

Strokes are in page px (origin top left, y down). The .rm format measures x from the page's
horizontal centre, so the writer shifts every point by half the page width: the portrait canvas
width, or for a landscape page the long side (checked on an rM2).
"""
from __future__ import annotations

import math
import uuid
from io import BytesIO
from typing import Sequence

from rmscene import read_tree
from rmscene import scene_items as si
from rmscene.crdt_sequence import CrdtSequenceItem
from rmscene.scene_stream import (
    AuthorIdsBlock,
    MigrationInfoBlock,
    PageInfoBlock,
    SceneGroupItemBlock,
    SceneInfo,
    SceneLineItemBlock,
    SceneTreeBlock,
    TreeNodeBlock,
    write_blocks,
)
from rmscene.tagged_block_common import CrdtId, LwwValue

from .devices import Device
from .vectorize import Stroke

ROOT_ID = CrdtId(0, 1)
FIRST_LAYER_ID = CrdtId(0, 11)  # device files always use 0:11 for the first layer
WRITER_VERSION = "3.2.2"


def page_centre_x(dev: Device, landscape: bool = False) -> float:
    """Where .rm x = 0 lies, in page px: the middle of the page as it is shown."""
    return (dev.height if landscape else dev.width) / 2


def to_rm_line(s: Stroke, dev: Device, *, landscape: bool = False) -> si.Line:
    cx = page_centre_x(dev, landscape)
    pts = []
    for i, (x, y) in enumerate(s.points):
        nx, ny = s.points[min(i + 1, len(s.points) - 1)]
        ang = math.atan2(ny - y, nx - x) % (2 * math.pi)
        pts.append(si.Point(
            x=x - cx,  # .rm x origin is the horizontal page centre
            y=y,
            speed=0,
            direction=int(ang / (2 * math.pi) * 255) & 0xFF,
            width=int(round(s.width * 4)),  # stored in quarter pixels
            pressure=255,
        ))
    # rmc renders fineliner at ~1.8 * thickness_scale px; the device value is to be verified.
    return si.Line(color=s.color, tool=s.tool, points=pts,
                   thickness_scale=s.width / 1.8, starting_length=0.0)


def rm_page(layers: Sequence[tuple[str, Sequence[Stroke]]], dev: Device, author: uuid.UUID,
            *, active_layer: int = -1, landscape: bool = False) -> bytes:
    """One page with the given (name, strokes) layers, bottom to top. `active_layer` is the index
    of the layer selected when the page opens (default: the top one). See layers.Page for the
    higher-level form."""
    if not layers:
        raise ValueError("a page needs at least one layer")
    counter = [100]

    def next_id():
        counter[0] += 1
        return CrdtId(1, counter[0])

    layer_ids = [FIRST_LAYER_ID] + [next_id() for _ in layers[1:]]
    blocks = [
        AuthorIdsBlock(author_uuids={1: author}),
        MigrationInfoBlock(migration_id=CrdtId(1, 1), is_device=True),
        PageInfoBlock(loads_count=1, merges_count=0, text_chars_count=0, text_lines_count=0),
        SceneInfo(
            current_layer=LwwValue(CrdtId(0, 0), layer_ids[active_layer]),
            background_visible=LwwValue(CrdtId(0, 0), True),
            root_document_visible=LwwValue(CrdtId(0, 0), True),
            paper_size=dev.paper_size,
        ),
    ]
    blocks += [SceneTreeBlock(tree_id=lid, node_id=CrdtId(0, 0), is_update=True, parent_id=ROOT_ID)
               for lid in layer_ids]
    blocks.append(TreeNodeBlock(si.Group(node_id=ROOT_ID)))
    for lid, (name, _) in zip(layer_ids, layers):
        blocks.append(TreeNodeBlock(si.Group(node_id=lid, label=LwwValue(next_id(), name),
                                             visible=LwwValue(CrdtId(0, 0), True))))
    left = CrdtId(0, 0)
    for lid in layer_ids:
        item_id = next_id()
        blocks.append(SceneGroupItemBlock(parent_id=ROOT_ID, item=CrdtSequenceItem(
            item_id=item_id, left_id=left, right_id=CrdtId(0, 0), deleted_length=0, value=lid)))
        left = item_id
    for lid, (_, strokes) in zip(layer_ids, layers):
        left = CrdtId(0, 0)
        for s in strokes:
            item_id = next_id()
            blocks.append(SceneLineItemBlock(parent_id=lid, item=CrdtSequenceItem(
                item_id=item_id, left_id=left, right_id=CrdtId(0, 0), deleted_length=0,
                value=to_rm_line(s, dev, landscape=landscape))))
            left = item_id
    buf = BytesIO()
    write_blocks(buf, blocks, options={"version": WRITER_VERSION})
    return buf.getvalue()


def read_layers(rm: bytes) -> list[tuple[str, list[si.Line]]]:
    """[(layer name, [Line, ...])] of a .rm page, bottom to top (for tests and inspection)."""
    tree = read_tree(BytesIO(rm))
    out = []
    for child in tree.root.children.values():
        if isinstance(child, si.Group):
            label = child.label.value if child.label is not None else ""
            out.append((label, [c for c in child.children.values() if isinstance(c, si.Line)]))
    return out
