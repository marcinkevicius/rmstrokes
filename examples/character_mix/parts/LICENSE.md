# Open Peeps parts: CC0 1.0

The SVG files in this folder are parts of **Open Peeps**, a hand-drawn illustration library by **Pablo Stanley**
(part of the Open Doodles project), from <https://www.openpeeps.com/>.

Open Peeps is dedicated to the public domain under the **Creative Commons CC0 1.0 Universal** public domain
dedication: <https://creativecommons.org/publicdomain/zero/1.0/>. The site says (checked 2026-10-26):

> Free for commercial and personal use under CC0 License.

> The library is in the public domain under the CC0 License

CC0 asks for nothing in return; we credit the author anyway (here, in the package's ATTRIBUTION.md and in
small print on the generated page).

## What we changed

Each file is one part (a body, a head, a face, facial hair or an accessory) cut out of one of the per-peep SVGs the
site serves, `https://cdn.prod.website-files.com/5e51c674258ffe10d286d30a/<id>_peep-<n>.svg`. Each SVG is a bust
drawn in a 240 x 324 frame. The cut keeps the part's paths unchanged, folds the groups' translations into one
`transform`, writes the inherited fill onto each path, crops the `viewBox` to the part (in the bust's coordinates,
so parts cut from different peeps still line up), and drops the editor's metadata, ids and comments. The table in
ATTRIBUTION.md lists the source file and both SHA-256 hashes for every part.
