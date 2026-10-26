# Attribution

Everything in this repository is MIT-licensed ([LICENSE](LICENSE)) and original to this project, **except the fonts
and the Open Peeps parts below**. This file lists every file that isn't plain source code: fonts, SVG art and images, where it comes from,
and its licence. If you add such a file, add it here in the same change.

## Fonts: `src/rmstrokes/fonts/` (SIL Open Font License 1.1)

Three faces of Atkinson Hyperlegible Next, bundled **unmodified**. The family's full licence is next to them
(`OFL-AtkinsonHyperlegibleNext.txt`), and the wheel ships it (`license-files` in `pyproject.toml`). Other fonts
aren't bundled: a font package brings them, with its own licences (`rmstrokes/fonts.py`).

| File | Use | Licence | Source | SHA-256 |
|---|---|---|---|---|
| `AtkinsonHyperlegibleNext-Regular.ttf` | design system (`default`, `color`): labels, body, fields | OFL 1.1, [OFL-AtkinsonHyperlegibleNext.txt](src/rmstrokes/fonts/OFL-AtkinsonHyperlegibleNext.txt). Copyright 2020-2024 The Atkinson Hyperlegible Next Project Authors (Braille Institute of America), no Reserved Font Name | [googlefonts/atkinson-hyperlegible-next](https://github.com/googlefonts/atkinson-hyperlegible-next) `fonts/ttf/`, commit `7925f50f649b3813257faf2f4c0b381011f434f1` | `88ed5c31a71584c7772963b02d04bef1eb7e3d2e9c8b9cb204339b1f82cf432c` |
| `AtkinsonHyperlegibleNext-Italic.ttf` | same | same | same | `b7f8f03ceb28ebadb2de2332b2e869a00e8dbfb5c8e00fdbb06385770c8227e7` |
| `AtkinsonHyperlegibleNext-SemiBold.ttf` | same | same | same | `8e2fff779f35ac25239656bb0f3b2bd35959a2009e3dd21a12141c3b9030362b` |

- The OFL allows bundling and redistributing these fonts, commercially too, as long as they aren't sold on their own
  and the licence goes with them.
- Generated PDFs embed **subsets** of the fonts; the OFL allows embedding in documents, and a document made with
  them is not itself under the OFL.
- A modified font (a subset you ship as a file, an instance cut from a variable font) may not keep the Reserved Font
  Name. Replace the files only with upstream's own static files, and update the table and the hashes.
- `.gitignore` ignores font files everywhere except `src/rmstrokes/fonts/*.ttf`, so a font can't be committed by
  accident elsewhere, and the bundled ones can't be lost to a blanket `*.ttf` rule.

## SVG art and images

| Files | Author | Licence |
|---|---|---|
| `tests/strokes_helpers.py` inline test SVG | original | MIT |
| `src/rmstrokes/shapes.py` primitives, `src/rmstrokes/strokefont.py` single-line font | original, drawn in code | MIT |
| `docs/intro/*` | rendered by this package | MIT |
| `docs/images/pages.png` | rendered by this package; shows the Open Peeps parts below | MIT; the parts CC0 1.0 |
| `docs/how-a-page-is-built/*` | rendered by this package (`rmstrokes explain`); the `character-mix-*` pictures show the Open Peeps parts below | MIT; the parts CC0 1.0 |

## Open Peeps parts: `examples/character_mix/parts/` (CC0 1.0)

The character mix example's bodies, heads, faces, facial hair and accessories are parts of **Open Peeps** by **Pablo
Stanley**, from <https://www.openpeeps.com/>, which the site puts in the public domain under
[CC0 1.0](https://creativecommons.org/publicdomain/zero/1.0/): "Free for commercial and personal use under CC0
License." (checked 2026-10-26). CC0 needs no credit; we give it anyway, here, in
[parts/LICENSE.md](examples/character_mix/parts/LICENSE.md) and in small print on the page.

Each part was cut from one of the per-peep SVGs the site serves (a 240 x 324 bust): its paths unchanged, the
groups' translations folded into one transform, the inherited fill written onto each path, the viewBox cropped to
the part in the bust's coordinates (so the parts line up), and the editor's ids and metadata dropped. These are
modified files, which CC0 allows.

| File | Part | Source | Source SHA-256 | SHA-256 |
|---|---|---|---|---|
| `body-striped-tee.svg` | `body/Striped-Tee` | [peep-12.svg](https://cdn.prod.website-files.com/5e51c674258ffe10d286d30a/5e535195d87131f9760b1c69_peep-12.svg) | `aec461d88d45338a178f1df67f8739f16a9a6ab0fe342d2240de3fbcfc92e74c` | `c6ff8374e2b7d4ff093fe48f9c9011137386c8c880b1c5b7fc828c9ec27414b9` |
| `body-hoodie.svg` | `body/Hoodie` | [peep-51.svg](https://cdn.prod.website-files.com/5e51c674258ffe10d286d30a/5e53578d550b76b873f53c46_peep-51.svg) | `63dc0870b362b0f66616f5f667d8faf3818007cc87f257e76c7de099a2e92088` | `ead81c780d4762692892dcfc6ed236aaaf468db54ff1dae644c2257b691c5bb3` |
| `body-blazer.svg` | `body/Blazer-Black-Tee` | [peep-105.svg](https://cdn.prod.website-files.com/5e51c674258ffe10d286d30a/5e535dd92b568a729c1c42f5_peep-105.svg) | `c590bb4b6893779edc11dfebdc0d398788bffec885540c75020e9f751515c5b7` | `18f74f56a0c43ba3316771b8f210d7e21234f243927b00ece50f7d8e7a97942f` |
| `body-dress.svg` | `body/Dress` | [peep-1.svg](https://cdn.prod.website-files.com/5e51c674258ffe10d286d30a/5e532a2aeba259dc7140a0e2_peep-1.svg) | `e13aab7eadf45db5feb55d50f1812baf7de88f34b34580ed47055185a3d12f39` | `3d5f41f223103cf7d0a18e0600dea262c60b76d5af53ffb45f67a8ec60d24935` |
| `head-afro.svg` | `head/Afro` | [peep-19.svg](https://cdn.prod.website-files.com/5e51c674258ffe10d286d30a/5e5352709588e06bd47b75e0_peep-19.svg) | `263a36dd017aa7fa602bf8404d067bb9e71882cbc68526c5c597050f95baebcc` | `9bbf20cb04557fc68eaffae75ee3cb763bae030f6697dab7c540ffb2961bd4c5` |
| `head-bun.svg` | `head/Bun` | [peep-35.svg](https://cdn.prod.website-files.com/5e51c674258ffe10d286d30a/5e53552ff5fa1a9d22f727e2_peep-35.svg) | `29cb60cb74484833d78767c58372ee07a86980b968ee7d0134f90f0927eb915e` | `9c22afba8c7a878ab5265dbf44056b7e50e203974f00a113862c415d16ca758f` |
| `head-long-curly.svg` | `head/Long-Curly` | [peep-23.svg](https://cdn.prod.website-files.com/5e51c674258ffe10d286d30a/5e535367f5fa1a2eedf59e1d_peep-23.svg) | `402738df3c7912e517186f89f498e8f976de6df8270558581ea05f9071c8c856` | `f21ab736ed8041f4673328a394fcfbaf9e53ffadc944da93ac0cda3242839aaa` |
| `head-mohawk.svg` | `head/Mohawk` | [peep-53.svg](https://cdn.prod.website-files.com/5e51c674258ffe10d286d30a/5e5357c17371bbccb99ecadf_peep-53.svg) | `b946abb33162591bd9efe343b14c8354d35fc35b5093d58790876f22c4773d35` | `f6b8323f115729753c6df94893cfdd2755ec132246523554ee67c6e198592f6b` |
| `head-hijab.svg` | `head/Hijab` | [peep-63.svg](https://cdn.prod.website-files.com/5e51c674258ffe10d286d30a/5e5358fb9b55b0b0f453f5f5_peep-63.svg) | `fd24acbb3b165d54a6a5c1dacd2e75ebfbff832d134c6f6d0f437c83fd1bb2f2` | `93a118c5eb09482f030bf576f36e169ab30ce3cc6560031fd61002a7af51b414` |
| `head-beanie.svg` | `head/hat-beanie` | [peep-73.svg](https://cdn.prod.website-files.com/5e51c674258ffe10d286d30a/5e535a2b8e24938384074dac_peep-73.svg) | `9e43b37c06d5feb90a89f09738935e6a9df84294697331edc7dfa7de93a6fb64` | `6221dcbbb8b1b346b2bc7b492b0100b31d82af8585623aa8618d455afb465709` |
| `face-smiling.svg` | `face/Smiling` | [peep-13.svg](https://cdn.prod.website-files.com/5e51c674258ffe10d286d30a/5e5351b17371bb6c489ad0cc_peep-13.svg) | `829e09851dee7485d0e77dea6c3f2487ecf87b64dd76ff2609d2f7738e805d8c` | `7dbdd81c8acee47fe565620e393c66ef33b6ba027b439c8b518a496851204ebc` |
| `face-grin.svg` | `face/Happy-Grin` | [peep-5.svg](https://cdn.prod.website-files.com/5e51c674258ffe10d286d30a/5e53508c8becbf15dd4f829c_peep-5.svg) | `faefcf18701164e09c98a4c69e39a890c61bb72050c79e5a6d6173384f31612e` | `29aafcf99c8f41d1cd7a74d7a4fc3873f6e744c235960a65e335ceb1535c7c31` |
| `face-awe.svg` | `face/Awe` | [peep-10.svg](https://cdn.prod.website-files.com/5e51c674258ffe10d286d30a/5e53515e2b568a43f515edd5_peep-10.svg) | `6c24c4a1cb8e37cef8042b8405183cff35482e50809d30c232dc07de14b6339d` | `2e40988f1d4eef61823b1c8c49bc5f92b57180b115f6751edad27e5a0652a02a` |
| `face-suspicious.svg` | `face/Suspicious` | [peep-53.svg](https://cdn.prod.website-files.com/5e51c674258ffe10d286d30a/5e5357c17371bbccb99ecadf_peep-53.svg) | `b946abb33162591bd9efe343b14c8354d35fc35b5093d58790876f22c4773d35` | `c0c5fb3b6f4b3056c7fdfcd0e22a260cae1987f9870ff9e60682e8a5b9aa39d4` |
| `face-tired.svg` | `face/Tired` | [peep-75.svg](https://cdn.prod.website-files.com/5e51c674258ffe10d286d30a/5e535a648e249323fd077d2b_peep-75.svg) | `813c9a0692f3e8c19436a31adf2e50d842642d60e3c1f90497e0035f3047d87e` | `c621f62013c2645344c08c41116fd6df53a90679be0b9aad3fa25fb2a813652b` |
| `face-cute.svg` | `face/Cute` | [peep-39.svg](https://cdn.prod.website-files.com/5e51c674258ffe10d286d30a/5e535637d87131637b0e4379_peep-39.svg) | `048fb4da33ea8dc58b47f0aa3e3b69afef94fc2f548bfbe037c72f2ae1d47075` | `fdf1312ff6efa402c33ccc8ed97918778712b8a8b2a1e4f0e324f0a63f4db9d6` |
| `beard-full.svg` | `facial-hair/Full` | [peep-10.svg](https://cdn.prod.website-files.com/5e51c674258ffe10d286d30a/5e53515e2b568a43f515edd5_peep-10.svg) | `6c24c4a1cb8e37cef8042b8405183cff35482e50809d30c232dc07de14b6339d` | `1a8f0beb098a4eb6eda33a0764bbdb2f2b084046c14263e0bed17b1cece7714e` |
| `beard-moustache.svg` | `facial-hair/Moustache-7` | [peep-97.svg](https://cdn.prod.website-files.com/5e51c674258ffe10d286d30a/5e535cf47488c27eb04a70d1_peep-97.svg) | `96dfeabba71db9741be210070ee7fca6c632a26e166fa85e3258f90a04ed03ee` | `30267a02fa1043496138eedbc18c5ac3cdc1c5a14101a286f5b0d6c6def7c073` |
| `beard-goatee.svg` | `facial-hair/Goatee-1` | [peep-39.svg](https://cdn.prod.website-files.com/5e51c674258ffe10d286d30a/5e535637d87131637b0e4379_peep-39.svg) | `048fb4da33ea8dc58b47f0aa3e3b69afef94fc2f548bfbe037c72f2ae1d47075` | `07f8a3b0679c2a7a9b609f592afc191f401cf3f15c173f7b09be852452c240d1` |
| `glasses.svg` | `accessories/Glasses` | [peep-76.svg](https://cdn.prod.website-files.com/5e51c674258ffe10d286d30a/5e535a83d3992372c25556b9_peep-76.svg) | `e7271636a5b07e15b9b4e12aaf8d43e5cc45a2aecbf8381314cad65bf704810e` | `169a0a2c3ede2191b214f4bf8aa8b0f0e937f548fef2a8bce0de45b449f2b1a6` |
| `sunglasses.svg` | `accessories/Sunglasses` | [peep-25.svg](https://cdn.prod.website-files.com/5e51c674258ffe10d286d30a/5e535398d87131adfd0c974a_peep-25.svg) | `076176d83b23a9004f8727f7b0d491a66c504c6038c2af514c98fd0ff188f42e` | `b3bedb78f6bbc5c16c599bcddcc19466cc279dafca4b3944917b0d7ce6ed128a` |
| `eyepatch.svg` | `accessories/Eyepatch` | [peep-12.svg](https://cdn.prod.website-files.com/5e51c674258ffe10d286d30a/5e535195d87131f9760b1c69_peep-12.svg) | `aec461d88d45338a178f1df67f8739f16a9a6ab0fe342d2240de3fbcfc92e74c` | `8e29bd9b9b02cccaa5182ee679f10ca99a869acd72c0132abf1208fdef231245` |

No other third-party artwork, icon sets or clip art are included.

## Data

The built-in template (`src/rmstrokes/builtin/*.toml`) and the examples (`examples/`), with their texts and word
lists, are original to this project (MIT).

## Dependencies

Installed from PyPI, not bundled: reportlab (BSD-3-Clause), rmscene (MIT), shapely (BSD-3-Clause; its wheels bundle
the GEOS library, LGPL-2.1, as an unmodified shared library that rmstrokes uses only through shapely), svgelements (MIT), numpy (BSD-3-Clause). Development only: pytest (MIT), pypdf
(BSD-3-Clause), pypdfium2 (Apache-2.0 / BSD-3-Clause; bundles PDFium), Pillow (MIT-CMU). The `.rmdoc`/`.rm` format
notes in [docs/format-notes.md](docs/format-notes.md) credit the open-source projects they were learnt from.

## Trademarks

reMarkable is a trademark of reMarkable AS. This project is not affiliated with, endorsed by or sponsored by
reMarkable AS; the name is used only to say which tablets the files are for.
