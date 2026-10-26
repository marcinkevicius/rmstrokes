# reMarkable notebook format notes

The format isn't officially documented. These notes come from the open-source readers/writers below,
from real device files in rmscene's test fixtures, from early experiments, and from this package's
writer (`rmstrokes.rm`, `rmstrokes.rmdoc`). Anything marked **(unverified)** still has to be confirmed on a device.
Only the **reMarkable 2** has been checked on hardware; everything about the Paper Pro and Paper Pro Move is
unverified (their presets come from published specs).

Sources:
- [rmscene](https://github.com/ricklupton/rmscene) 0.8.0: reads and writes v6 `.rm`. We use it to write.
- [rmc](https://github.com/ricklupton/rmc): renders `.rm` to SVG/PDF. Its pen-width model is in `exporters/writing_tools.py`.
- [rmrl](https://github.com/rschroll/rmrl): older (v5 era) renderer. Useful for how PDF + annotations are merged.
- [ddvk/rmapi](https://github.com/ddvk/rmapi) `archive/file.go`: `.content` / `cPages` structs.
- [drawj2d](https://sourceforge.net/p/drawj2d/wiki/reMarkable/): an existing tool that already writes vector drawings as `.rm`/`.rmdoc`/`.rmn` strokes. It shows the approach works on real devices.
- [remarquee rmdoc package](https://pkg.go.dev/github.com/go-go-golems/remarquee/pkg/rmdoc): archive layout.
- [Andrew Doering, "Rebuilding my reMarkable daily journal"](https://andrewdoering.org/blog/2026/rebuilding-my-remarkable-daily-journal/): native templates and how `.content` UUIDs relate to `.rm` UUIDs.

## 1. `.rmdoc` package

An `.rmdoc` is a plain **zip**. (`.rmn` is the same thing as a tar, used by RCU.)

```
<docUUID>.content          JSON: document type, page list (cPages), view settings
<docUUID>.metadata         JSON: visibleName, parent folder, timestamps, type
<docUUID>.pdf              only for fileType "pdf": the original PDF
<docUUID>.epub             only for fileType "epub"
<docUUID>.pagedata         optional, legacy: one template name per line
<docUUID>/<pageUUID>.rm    one v6 scene file per page that has content
```

The writer (`rmstrokes.rmdoc`) writes the minimum set: `.content`, `.metadata`, the `.pdf`, and one `.rm` per page.
Thumbnails (`<docUUID>.thumbnails/`) and per-page `-metadata.json` (a v5 leftover) are left out.
The device seems to regenerate them **(unverified)**.

### `.metadata`

```json
{"createdTime": "<ms>", "lastModified": "<ms>", "lastOpened": "<ms>", "lastOpenedPage": 0,
 "parent": "", "pinned": false, "type": "DocumentType", "visibleName": "My document"}
```

`parent: ""` puts the document in the root folder. `type` is `CollectionType` for folders.

### `.content` (formatVersion 2 / "cPages" schema, firmware 3.x)

The older schema used a flat `"pages": [uuid…]` list plus `redirectionPageMap`. Firmware 3.x replaced it
with `cPages`, a set of CRDT registers: every value is `{"timestamp": "<author>:<counter>", "value": …}`.

```json
{
  "cPages": {
    "lastOpened": {"timestamp": "1:1", "value": "<pageUUID>"},
    "original":   {"timestamp": "0:0", "value": -1},          // PDF: number of pages in the PDF
    "pages": [{
      "id": "<pageUUID>",
      "idx": {"timestamp": "1:2", "value": "ba"},             // fractional sort key ("ba", "bb", ...)
      "template": {"timestamp": "1:1", "value": "Blank"},     // notebooks: template name
      "redir": {"timestamp": "1:2", "value": 0}               // PDFs: which PDF page sits under this page
    }],
    "uuids": [{"first": "<author UUID>", "second": 1}]        // author index 1 -> UUID
  },
  "fileType": "notebook" | "pdf" | "epub",
  "formatVersion": 2,
  "orientation": "portrait",
  "pageCount": 1,
  "coverPageNumber": 0, "documentMetadata": {}, "extraMetadata": {}, "fontName": "",
  "lineHeight": -1, "pageTags": [], "tags": [], "sizeInBytes": "…",
  "textAlignment": "justify", "textScale": 1, "zoomMode": "bestFit"
}
```

- Inserting a page means picking an `idx` key between its neighbours. Deleting one adds `"deleted": {"value": 1}`.
- `cPages.uuids[0].first` should be the same author UUID as in the `.rm` `AuthorIdsBlock`.
  rmscene reads and writes that block with `UUID(bytes_le=…)`, so `str(uuid)` gives the form `.content` expects.
  Doering found the same thing from the other side: a naive reader prints the first three groups byte-swapped.
- Real device files carry more fields (`customZoom*`, `sizeInBytes`, `viewBackgroundFilter`, …).
  We don't know whether the device rejects a file without them **(unverified, the first thing to check)**.

## 2. `.rm` v6 page file

Header: `reMarkable .lines file, version=6` padded with spaces to 43 bytes. After that comes a stream of
**tagged blocks**: `[u32 length][u8 unknown][u8 min_version][u8 cur_version][u8 block_type]` + payload.
Each payload is a set of tagged fields (`tag = index<<4 | type`: id, bool, varuint, float, double, sub-block).
Unknown trailing bytes are kept, so newer firmware stays readable.

The blocks we write (copied from the structure of rmscene's device fixture `Normal_A_stroke_2_layers_v3.3.2.rm`):

| Block | Type | Purpose |
|---|---|---|
| `AuthorIdsBlock` | 0x09 | author index → UUID (index 1 = this device or generator) |
| `MigrationInfoBlock` | 0x00 | `migration_id=1:1, is_device=true` |
| `PageInfoBlock` | 0x0A | load/merge counters, text char/line counts |
| `SceneInfo` | 0x0D | current layer, background visible, **paper_size** (Paper Pro: `(1620, 2160)`; rM2 files omit it) |
| `SceneTreeBlock` | 0x01 | declares a tree node (`tree_id`) and its parent |
| `TreeNodeBlock` | 0x02 | node properties: `label` (layer name), `visible`, optional text anchor |
| `SceneGroupItemBlock` | 0x04 | puts a group into a parent's ordered child list (CRDT sequence) |
| `SceneLineItemBlock` | 0x05 | one stroke (`Line`) in a group's child list |
| `RootTextBlock` | 0x07 | typed text (not used here) |
| `SceneGlyphItemBlock` | 0x03 | PDF/EPUB text highlights (not used here) |
| `SceneTombstoneItemBlock` | 0x08 | deleted item (`deleted_length>0`, no value) |

### Scene tree and layers

```
root group (0:1)
 ├─ Layer group  "Layer 1" (0:11)      <- always id 0:11 on device files
 │    ├─ Line, Line, ...               <- strokes can sit directly in the layer...
 │    └─ Group (anchored to text)      <- ...or in sub-groups, e.g. strokes anchored to typed text
 │         └─ Line ...
 └─ Layer group  "Layer 2" (1:N)
      └─ Line ...
```

- **A layer is just a direct child group of the root.** Its name is the group's `label`, and it can be hidden with `visible`.
  Layer order is the order of the root's `SceneGroupItemBlock` sequence (linked by `left_id`/`right_id`).
  Children later in the sequence draw on top.
- Every item has a CRDT id `(author, counter)`, and a sequence item points at its left/right neighbours.
  The device merges edits from several clients with these ids. For a generated file, monotonically increasing ids
  and `left_id = previous item` are enough. rmscene's fixtures and rmc both read such files fine.
- `SceneInfo.current_layer` chooses the active layer when the page opens. rmstrokes points it at the page's
  active layer (`layers.Page.active`, by default the top stroke layer); whether the device honours it is **unverified**.
- With the layer API (`rmstrokes.layers`) a page has any number of named stroke layers plus an optional empty
  handwriting layer (below them by default, so a lasso on a stroke layer never picks up notes). The first layer gets
  `0:11`. Each object's strokes (a token with its name tag, say) are consecutive in its layer's sequence.

### Strokes (`Line`)

| Field | Notes |
|---|---|
| `tool` | `Pen` enum: `FINELINER_2`=17 (uniform width, the right choice for solid fills), `BALLPOINT_2`=15, `MARKER_2`=16, `PENCIL_2`=14, `SHADER`=23, `HIGHLIGHTER_2`=18 … (`*_1` ids are pre-v2 tools) |
| `color` | `PenColor`: BLACK 0, GRAY 1, WHITE 2, YELLOW, GREEN, PINK, BLUE, RED, … HIGHLIGHT 9 (+`color_rgba`) and newer Paper Pro colours 10-13 |
| `thickness_scale` | f64. rmc renders a fineliner at about `1.8 × thickness_scale` px |
| `starting_length` | f32, 0 for new strokes |
| `points` | v2 point = `x f32, y f32, speed u16, width u16, direction u8, pressure u8` (14 bytes) |
| `move_id` | optional, set by the device after a lasso move **(our guess from the field name)** |

**Coordinates:** pixels. **x = 0 is the horizontal centre of the page** (x runs from −W/2 to +W/2), and
**y = 0 is the top**, increasing downwards. Strokes may go past the page; on the device a notebook page scrolls down.
`width` is stored in quarter pixels (rmscene's v1 conversion does `width/4`), and `direction` is the angle
scaled to 0-255.

Size: 14 bytes per point plus about 40 bytes per stroke. With 4 px point spacing, one icon-style SVG figure drawn
154 px tall on rM2 costs:

| Style | Strokes | Points | `.rm` bytes |
|---|---|---|---|
| `filled` (outline + dense fill) | 7 | ~755 | ~10.6 KiB |
| `white-fill` (outline + opaque white fill) | 16 | ~700 | ~10.2 KiB |
| `outline` | 11 | ~300 | ~4.6 KiB |

Zip compresses this about 2.5-3×.

### How an SVG becomes strokes (`rmstrokes.vectorize`)

1. svgelements parses the SVG in paint order. Every shape counts (`<circle>`s too). Colours are classified
   dark/light by luminance, and stroke widths come from each element.
2. shapely composites the **dark** and **light** regions. Fills use the element's fill rule, strokes are buffered with
   their own cap/join style, and later paint covers earlier paint.
3. **`filled`**: the dark region already contains the outline bands, so the strokes are
   - one **contour line per boundary ring** of the region eroded by half a pen width. The round ink edge then lands
     exactly on the shape edge, around the outside and around every light hole, so hatch-line ends never form an
     edge (they look scalloped);
   - a **boustrophedon scanline hatch** inside the contour (0.8 pen spacing, overlapping the contour by ¼ pen so
     narrow spikes close up);
   - **thin features** the eroded core can't reach: the SVG centreline where it stays at least half a pen from light
     areas, otherwise a contour line at the bit's own thickness (≈ 2·area/perimeter), grown slightly into its
     neighbours so no seams show.
4. **`white-fill`** hatches the light interior with white ink, then the black outline centrelines and dark details
   go on top; **`outline`** leaves out the white ink.
5. Strokes are computed once per (drawing, box size, style) at the box's origin, then translated (and turned) per
   placement.

Primitive shapes (`rmstrokes.shapes`: circle, star, pin, tag, arrow, ...) and stroke-font text
(`rmstrokes.strokefont`) go through the same contour-and-hatch fill.

## 3. Combining a PDF background with stroke layers

Three ways to get a fixed background under movable strokes:

1. **PDF document + annotation layers** (what rmstrokes does).
   Set `fileType: "pdf"`, ship `<docUUID>.pdf`, and point each page's `cPages.pages[].redir` at a PDF page index.
   The page's `.rm` is the same v6 scene file as in a notebook. It can have **several layers**, and **the PDF is always drawn
   beneath every layer**. `SceneInfo.background_visible` probably toggles it. The PDF is not part of the
   scene, so the lasso can't select it and the background can't be moved by accident.
   - We size the PDF at device aspect ratio with `1 px = 72/dpi pt` (rmc 0.3.0 uses a fixed `72/226` for every
     file, i.e. the rM2 value, even for Pro/Move files). This should make PDF
     content and strokes line up 1:1. **Check alignment on each device** (a stroke drawn over a printed mark should sit on it).
     PDFs with another aspect ratio get letterboxed, and the stroke↔PDF mapping then changes.
   - On the device, pages added to a PDF document are blank (no PDF page under them).
   - Multi-page: the PDF has N pages, `cPages.original = N`, and page *i* has
     `redir = i` and `idx` keys `ba`, `bb`, … (sorted order = page order). Each page gets its own `.rm`.
   - Links (e.g. a contents page): ordinary PDF link annotations
     (`/Link` with a direct `/Dest [page /Fit]`) and the PDF has an outline. Since page *i* of the document is PDF
     page *i*, a link's target page is also the notebook page. **Unverified:** whether the tablet follows a tapped
     link in a PDF-backed `.rmdoc` (and whether it still does once the user inserts pages), and whether it shows
     the outline. A page with nothing to move still gets a `.rm` with one empty layer so it can be written on.
2. **Background as strokes in a lower layer.** Everything is native and the file is self-contained.
   The background is selectable too, though, unless the lasso only acts on the active layer **(unverified, critical)**,
   and hatched areas cost many times the bytes of the movable strokes.
3. **Notebook + template.** A page refers to a template by name (`"template": "Blank"`). Built-in templates live in
   `/usr/share/remarkable/templates/`. A custom template needs SSH/developer mode on the device,
   so it doesn't work on a stock tablet.

A **notebook** (`fileType: "notebook"`) can't embed a PDF background. That only works as a PDF document.
"PDF document whose pages are the backgrounds, movable things as strokes on annotation layers" is the shape
rmstrokes uses, provided lasso and move behave the same on PDF annotations as in notebooks (they do on the rM2).

**Landscape pages:** the document's `orientation` is `"landscape"` and the PDF pages are landscape-sized. The tablet
keeps 1 px = 72/dpi pt and measures `.rm` x from the centre of the page as shown (half the long side). Checked on an
rM2. A document has one orientation; rmstrokes refuses to mix them.

## 4. Device canvases

| Preset | Portrait px | PPI | `SceneInfo.paper_size` | Source |
|---|---|---|---|---|
| reMarkable 2 | 1404 × 1872 | 226 | not written | [reMarkable compare page](https://remarkable.com/store/remarkable-paper/pro/details/compare); rmc uses the same constants |
| Paper Pro | 1620 × 2160 | 229 | `(1620, 2160)` (seen in rmscene fixture `Color_and_tool_v3.14.4.rm`) | [reMarkable compare page](https://remarkable.com/store/remarkable-paper/pro/details/compare) |
| Paper Pro Move | 954 × 1696 | 264 | `(954, 1696)`? **(unverified)** | [Liliputing](https://liliputing.com/remarkable-paper-pro-move-is-a-smaller-color-e-ink-writing-tablet-with-a-7-3-inch-display/), [PCWorld review](https://www.pcworld.com/article/2953509/remarkable-paper-pro-move-test-small-e-ink-tablet-with-a-real-paper-feel.html) (7.3", 1696 × 954, 16:9) |

Each preset only changes the canvas width/height, the x-centre offset, and `paper_size`. Layouts are in mm
(`Device.mm`), so physical sizes are about the same on every device. Only the rM2 preset is marked
`verified=True`; the Paper Pro and Move presets are kept and generated, but **unverified** on hardware.
Cross-device behaviour is untested: what happens when a file made with the rM2 preset is opened on a Pro, or the reverse.

## 5. What the device writes after a lasso move

**Unverified.** Whether the tablet rewrites the points of moved strokes or stores a transform, whether it adds
`move_id`, and whether it keeps our `.content` as written all have to come from a real device export: generate a
document, move a few objects with the lasso, export it again and compare the two files.
