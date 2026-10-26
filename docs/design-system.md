# Design system

The type, colour, line and spacing rules every template draws with, as tokens in
[`rmstrokes/design.py`](../src/rmstrokes/design.py). This page gives the values and why each one was chosen.
`rmstrokes specimen -o out/` prints all of them on the device they are for.

```bash
rmstrokes specimen -o out/                         # rm2 in "default", pro in "color": .rmdoc, .pdf, .png
rmstrokes specimen --device all --theme all -o out/  # every device in every theme
```

**Status.** Only the reMarkable 2 has been checked on hardware. The Paper Pro colours, and everything on the Paper Pro
Move, come from published specs and screen-independent rules (contrast, CIELAB). Treat them as **unverified** until
someone loads the specimen on those tablets. The specimen prints "unverified on device" in its footer for those
devices.

## Why

E-ink at about 226 ppi is unforgiving with type and colour that look fine on a screen:

- **High-contrast faces** (Didones and other display serifs) have hairlines of about 1 px at label sizes, so they
  break up and the letters lose their shape.
- **Monospace for labels** spends width on every narrow letter. Labels look like code, and long names get shrunk or
  cut.
- **Capitals-only and decorative faces** suit a short label at the edge of a page and nothing else.
- **Pale greys and decorative patterns** vanish or shimmer as the panel refreshes.

The design system sets one modern, highly legible default for every template, so documents from different templates
look like they belong together. A package that wants a different look registers it as a theme of its own (see below).

## Themes

| Theme | What it is | For |
|---|---|---|
| `default` | The system: Atkinson Hyperlegible Next, Source Serif 4 titles (when installed), the greyscale palette | the reMarkable 2, and any tablet |
| `color` | The same type and greys, plus the Paper Pro palette (accents, a contrasting pair, colour pens for tokens) | Paper Pro and Paper Pro Move (**unverified**) |

Every template takes `--theme` (`theme = "..."` in a recipe). `Template.themes()` defaults to the design themes. A template with
its own theme names maps them to a design theme with `theme_styles`. A name that isn't mapped (a theme of the
template's own, say) draws with the template's `fallback_style` (`default` unless it sets another).

Another package adds a theme with `design.register_theme(name, factory)`, where `factory(device)` returns a
`design.Style` (`design.make_palette` builds the palette from your grey tokens). Once registered, it is a design
theme like the others: `get_style`, `--theme`, recipes and the specimen all accept it. Pages get the resolved tokens as `ctx.style` (a `design.Style`):

```python
def pages(self, values, ctx):
    s = ctx.style
    def draw(p):
        s.draw_text(p, values["title"], s.margin(), s.mm(14), "title")
        s.knockout_text(p, "Notes", s.margin(), s.mm(40), "caption")  # over ruled lines
        p.line(x0, y, x1, y, s.line("rule"), s.color("rule"))
```

In data templates, `font` takes a role name (`font = "caption"`) and `color` / `fill` take a token
(`color = "muted"`, `fill = "accent-2-tint"`). Font file names and `#RRGGBB` still work.

**What uses it today.** The engine's own pages use the tokens: the intro page (always in the system style, colour
on a colour tablet; see [intro.md](intro.md)), write-in fields, tray labels and frames, the data-template
elements and the built-in `gaps` template.

## Typography

### Fonts

| Role | Default / color | Bundled with the engine? |
|---|---|---|
| UI, labels, body, fields | **Atkinson Hyperlegible Next** Regular, Italic, SemiBold | yes |
| Small print | Atkinson Hyperlegible Next Medium | no: SemiBold without it |
| Titles (optional display face) | **Source Serif 4 Subhead** Semibold | no: Atkinson SemiBold without it |
| Tabular numbers only | IBM Plex Mono Medium | no: Atkinson Regular without it (proportional figures) |

The engine bundles only the three Atkinson faces every page needs, so it renders on its own. The other faces are
found by name once a font package that ships them is installed (entry point group `rmstrokes.fonts`, see
`rmstrokes/fonts.py`) or their folder is registered with `fonts.add_font_source`; the built-in themes then use them
for the roles above. Without them, each of those roles takes the bundled face in `design.FALLBACK`.

**Atkinson Hyperlegible Next** (Braille Institute, 2025, SIL OFL 1.1) was designed for low-vision readers, and that is
close to what e-ink asks for. Its letterforms are built to be told apart: `I l 1`, `O 0` and `rn m` are distinct. Its
apertures are wide, so `c e a s` stay open when the panel smears an edge. Its strokes are sturdy and close to
monolinear, with no hairlines to lose. Reviews single out exactly this: it holds up at small sizes and low contrast.
The 2025 "Next" release has seven weights, and the static TTFs ship upstream, so we bundle the original files
(three of them).

Candidates we compared and why they lost:

- **Inter**: excellent, but tuned for screens at 11-16 px. Its tight apertures and the uniform `Il1` make it worse for
  labels you read in passing.
- **Source Sans 3**: lighter strokes. The regular weight looks thin on the rM2.
- **Nunito Sans**: friendly, but its round terminals blur at 7-8 pt.

**Source Serif 4** (Adobe, OFL, Reserved Font Name "Source") gives titles some warmth without a period look. The
engine doesn't bundle it; when a font package provides it, the `title` role uses the **Subhead** optical size, which
is drawn for 18-40 pt. It has less stroke contrast than the Display cut, so no
hairlines go missing, and it is sturdier than the text cut at title size. **Literata**, designed for e-readers, was the
other candidate. Upstream ships only the variable font, though, and cutting our own static instance would be a
modified font under the OFL.

The display face is **optional**. A template that wants an all-sans page can draw its title in the `heading` role or
in `AtkinsonHyperlegibleNext-SemiBold`.

**The monospace is used only** for numbers that have to line up in columns (the `numeric` role).

### Scale

Sizes are the font size (em) in mm. The same physical size works on the rM2 and the Pro, which have nearly the same
pixel density (226 and 229 ppi) and are held at the same distance. The Move's page is only 92 mm wide and is held
closer, so its big type is scaled down (title ×0.85, heading ×0.9, value ×0.92). Small type never shrinks: 2.5 mm is
the floor on every device.

| Role | Size | ≈ pt | Font (default) | Colour | Use |
|---|---|---|---|---|---|
| `title` | 6.4 mm | 18 | Source Serif 4 Subhead Semibold (else Atkinson SemiBold) | ink | page title, one per page |
| `heading` | 4.2 mm | 12 | Atkinson SemiBold | ink | section headings |
| `label` | 3.2 mm | 9 | Atkinson Regular | ink | names and labels on the page |
| `body` | 3.2 mm, leading 1.4 | 9 | Atkinson Regular | ink | instructions, running text |
| `value` | 3.6 mm | 10 | Atkinson Regular | ink | pre-filled values in write-in fields |
| `italic` | 3.2 mm | 9 | Atkinson Italic | muted | hints, subtitles |
| `caps` | 2.8 mm, +8 % tracking, capitals | 8 | Atkinson SemiBold | ink | short group labels ("SUMMARY") |
| `caption` | 3.0 mm | 8.5 | Atkinson SemiBold | ink-2 | what an area is ("Start here") |
| `field` | 2.8 mm | 8 | Atkinson Regular | muted | the label of a handwriting field |
| `small` | 2.5 mm | 7 | Atkinson Medium (else SemiBold) | muted | legends, notes; the smallest size |
| `numeric` | 3.2 mm | 9 | IBM Plex Mono Medium (else Atkinson Regular) | ink | tabular figures |

Weights: Regular for reading, SemiBold for anything that labels or heads, Medium for the smallest size (Regular at 7 pt
is too thin on e-ink, so without Medium it goes up to SemiBold, not down), Bold for rare emphasis where a font
package provides it.

Capitals get **+6 to 8 % letter spacing** (`caps`), because capitals set at the default spacing crowd together. Keep
caps for labels of one or two words. Anything longer is set in sentence case (`caption`), which reads faster.

Handwriting-field labels are deliberately small and `muted`: they say what goes on the line, and the handwriting is
what should stand out.

## Colour

### Greys (reMarkable 2)

The rM2 panel shows **16 grey levels**. Every grey in the ramp is a multiple of `0x11`, so it lands exactly on a level
instead of being dithered or rounded to its neighbour. Two greys need to be at least one level apart to look different.

| Token | Value | Contrast on white | May be used for |
|---|---|---|---|
| `ink` | `#000000` | 21:1 | text, outlines, everything that matters |
| `ink-2` | `#333333` | 12.6:1 | secondary text, captions |
| `muted` | `#555555` | 7.5:1 | the lightest **text**: field labels, hints, small print |
| `rule` | `#666666` | 5.7:1 | **thin lines** under 0.4 mm: writing lines, grids, frames |
| `guide` | `#888888` | 3.5:1 | lines of **0.35 mm and more** only: dotted outlines, guides |
| (`#AAAAAA`) | | 2.3:1 | avoid: too light for a line, too dark for a fill behind text |
| `surface-strong` | `#CCCCCC` | ink on it 13:1 | the darkest fill text may sit on |
| `surface` | `#DDDDDD` | ink on it 15.5:1 | bands, shaded areas |
| `surface-faint` | `#EEEEEE` | ink on it 18:1 | a hint of a fill. Never the only cue: it can vanish on some panels |
| `paper`, `knockout` | `#FFFFFF` | | white: behind labels over lines |

Minimum contrast against white (WCAG 2 ratio, `design.MIN_CONTRAST`) is stricter than on a screen. E-ink paper is a
light grey rather than white, there is no backlight, and greys are reproduced by the panel's waveform rather than
exactly:

- **text: 7:1** (WCAG AAA). That is `muted` (#555) or darker.
- **lines: 4.5:1**. That is `rule` (#666) or darker. Thin lines lose contrast to anti-aliasing as well.
- **guides: 3:1** (the WCAG non-text minimum). That is `guide` (#888), and only for lines 0.35 mm or wider.
- **fills: #CCCCCC or lighter**, so ink text on them stays above 7:1.

`grey_uses()` applies these rules. The specimen prints each grey's allowed uses, and `tests/test_design.py` checks
every token against them.

On the rM2, **only three fills tell apart reliably side by side**: `surface-strong`, `surface` and `surface-faint`. In
the greyscale themes the six accents fall back to these three greys, cycling. A fourth category needs a label or a
pattern (below).

### Paper Pro colour

The Paper Pro's "Canvas Color" panel is a modified **E Ink Gallery 3**, with cyan, magenta, yellow and white pigment
particles in every pixel. reMarkable compares it to newsprint, and reviewers describe the colours as clear but muted.
The panel shows thousands of colours in documents through dithering, but only nine pen colours for ink. In practice:

- **Strong, saturated darks render muddy and dithered.** Accent inks therefore sit at L\* 39-49 with moderate chroma
  (≤ 55), not at full saturation.
- **Very light tints wash out to paper.** Tints therefore sit at L\* 86-90 with chroma 12-23, light enough for ink text
  on them (≥ 14:1) and dark enough to stay visible.
- **The palette is small**: six hues, each an `ink` for lines and marks plus a `tint` for fills. Accent inks are at
  least ΔE 22 apart from each other, tints at least ΔE 13.

| Token | Hue | Ink | Tint | Ink on white | Pen colour for strokes |
|---|---|---|---|---|---|
| `accent-1`, `pair-a` | blue | `#2D5F9E` | `#C6DCF3` | 6.5:1 | BLUE |
| `accent-2`, `pair-b` | red | `#B5473A` | `#F2CFC8` | 5.3:1 | RED |
| `accent-3` | green | `#3E7B45` | `#D5E8C4` | 5.1:1 | GREEN |
| `accent-4` | amber | `#9A6B12` | `#F1DFB4` | 4.7:1 | YELLOW |
| `accent-5` | violet | `#6B4F96` | `#E8D3EC` | 6.6:1 | MAGENTA |
| `accent-6` | teal | `#1F7470` | `#C2E6E6` | 5.5:1 | CYAN |

Rules for colour:

- **Text stays in the greys.** Accent inks clear the line floor (4.5:1) but not all of them clear the text floor, so
  colour goes on lines, marks, fills and tokens, and labels stay `ink` or `ink-2`.
- **The pair (`pair-a`, `pair-b`) is blue against red.** It stays apart under the common colour blindnesses (deuteranopia,
  protanopia), and on a greyscale export they still differ in lightness. On the rM2 the template has to make them
  differ by form as well (solid against hatched discs).
- **Movable strokes use the tablet's own pen colours** (`style.pen("pair-a")`). PDF colours are approximated by
  dithering, but pen colours are what the tablet draws natively.
- **Colour is never the only cue.** Every colour page must still work when printed or viewed in grey. The specimen
  shows each accent's greyscale equivalent next to it.

The `color` theme on an rM2 is allowed but pointless: the tablet shows each colour as the grey of the same lightness.

## Lines

1 px is 0.112 mm on the rM2, 0.111 mm on the Pro and 0.096 mm on the Move. A line thinner than about 2 px comes out
broken and uneven after anti-aliasing and the e-ink waveform.

| Token | mm | rM2 px | Use |
|---|---|---|---|
| `hairline` | 0.25 | 2.2 | the thinnest printed line, in `ink` or `rule` only |
| `rule` | 0.30 | 2.7 | writing lines, grids |
| `line` | 0.40 | 3.6 | outlines, frames; from here `guide` grey is allowed |
| `strong` | 0.60 | 5.3 | the main area's border |
| `heavy` | 1.00 | 8.9 | the one thing that must stand out |
| `dot` | 0.35, gap 1.2 | | dotted lines (thinner dots vanish) |
| `hatch` | 0.25 at 1.4 pitch, 45° | | patterns, when nothing else works |

Lines, fills and text should keep their contrast floors **against each other** as well. A `guide` line on a `surface`
fill is about 2.6:1, which is too faint. On a fill, use `rule` or `ink`.

## Fills against patterns

**Fills first. Patterns only when there is no other way.** Decorative background patterns look busy, and on
e-ink they also cost legibility: hatching under text competes with the letters, and dense patterns shimmer as the
screen refreshes.

A pattern is allowed when **all** of these hold:

1. Two or more areas have to be told apart,
2. they can't be labelled directly (no room, or the label would sit on the thing being marked), and
3. the three reliable greys are already used, or the areas sit on top of each other (a pattern lets the area below show
   through).

Typical cases are the fourth category on an rM2, and the two sides of a pair on greyscale (solid against hatched discs). A
pattern is drawn as a `hatch` (0.25 mm lines, 1.4 mm pitch, 45°), clipped to the area, and never behind text.
Background textures and "paper" patterns are not used.

## Knock-outs

A label or a tag that sits on lines (ruled notes, a grid, a diagram) gets a **white knock-out**: an opaque white
area behind it with `knockout_pad` (0.6 mm) of clearance, so no line runs through the letters.

- **Printed labels**: `style.knockout_text(p, text, x, y, role)` draws a white rounded box sized to the text, then the
  text on it.
- **Name tags on movable tokens**: `NameTag(..., knockout=True)` fills the tag with **white pen strokes** inside the
  token's cluster. A white box printed on the page would stay put when the token moves, while white ink moves with it.
  The tag's outline is drawn after the white, and the white stops at the token's shape. Data templates set
  `name_tag = { knockout = true }`. It is opt-in.

The specimen's "Over ruled lines" section puts a token with a knock-out tag next to one without, on ruled lines, with
"ANA" written in each tag.

## Spacing and margins

Everything sits on a **1 mm grid**. Gaps use the steps **1, 2, 3, 4, 6, 8, 12, 16 mm**.

| Token | Value | Why |
|---|---|---|
| `margin` | rM2 8 mm, Pro 9 mm, Move 5 mm | clear of the bezel edge without wasting the Move's narrow page |
| `gutter` | 4 mm | between columns and blocks |
| `toolbar` | 14 mm | kept free at the left edge, where the open toolbar covers the page. `Style.safe_area()` is the page inside the margin and clear of this strip; the intro page, the built-in template and the examples keep everything inside it (the 14 mm is an estimate, not yet measured on any tablet) |
| `knockout_pad` | 0.6 mm | white around a knocked-out label |
| `write_pitch` | 8 mm | ruled writing lines; comfortable with the Marker at normal handwriting size |

## Sources

- E Ink Gallery 3 and the Paper Pro panel (CMY+W particles, newsprint-like muted colour, nine pen colours, thousands of
  colours in documents): [Engadget](https://www.engadget.com/mobile/tablets/the-new-remarkable-paper-pro-adds-a-color-display-120059067.html),
  [E Ink blog](https://blog.eink.com/new-remarkable-paper-pro),
  [Liliputing on Gallery 3](https://liliputing.com/e-ink-gallery-3-color-display-tech-coming-to-ereaders-more-colors-higher-contrast/).
- Atkinson Hyperlegible: [Pimp my Type review](https://pimpmytype.com/atkinson-hyperlegible/),
  [Adobe Fonts: Atkinson Hyperlegible Next](https://fonts.adobe.com/fonts/atkinson-hyperlegible-next),
  upstream [googlefonts/atkinson-hyperlegible-next](https://github.com/googlefonts/atkinson-hyperlegible-next).
- Source Serif 4 optical sizes: [adobe-fonts/source-serif](https://github.com/adobe-fonts/source-serif).
- Template line advice for the rM2 (2-3 px, mid greys): [Templacity](https://templacity.com/remarkable/remarkable-template-size/).
- Contrast: WCAG 2.2, success criteria 1.4.6 (contrast, enhanced) and 1.4.11 (non-text contrast).
- Licences, sources and file hashes: [ATTRIBUTION.md](../ATTRIBUTION.md).
