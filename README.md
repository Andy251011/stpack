# stpack

Turns one raw spatial transcriptomics sample folder into one standardised
`.tar.gz` containing only the files we need, plus a manifest recording what
was kept, what was dropped, and why.

Supports **Xenium** and **Visium** (including CytAssist).

## Install

```bash
git clone https://github.com/Andy251011/stpack && cd stpack
pip install -e .
```

No dependencies beyond the standard library.

## Use

```bash
# See what would be kept, without writing anything
stpack /path/to/xenium_mouse_brain --dry-run

# Package it
stpack /path/to/xenium_mouse_brain -o ./packaged

# Xenium: also keep transcripts.parquet (~174 MB, off by default)
stpack /path/to/xenium_mouse_brain -o ./packaged --with-transcripts

# Batch
for d in /data/raw/*/; do stpack "$d" -o ./packaged; done
```

From Python:

```python
from stpack import package_sample

manifest = package_sample("data/visium_lung", "packaged", sample_id="lung_A1")
```

## Output

```
xenium_mouse_brain.tar.gz
└── xenium_mouse_brain/
    ├── expression.h5
    ├── cells.parquet
    ├── cell_boundaries.parquet
    ├── nucleus_boundaries.parquet
    ├── image.ome.tif          # full 3D stack
    ├── image_mip.ome.tif      # 2D projection of the same stack
    ├── gene_panel.json
    ├── experiment.xenium
    ├── metrics_summary.csv
    ├── analysis/              # 10x clustering, diffexp, PCA, UMAP
    └── manifest.json
```

Names are standardised across platforms, so `expression.h5` means the same
thing whether the sample came from Xenium or Visium. The manifest records
each item's original vendor filename, size, and SHA-256.

## What gets kept

The decision table lives in `src/stpack/keeplists.py` — it is meant to be
read and argued with, not buried.

| Concept | Xenium | Visium |
|---|---|---|
| expression matrix | `cell_feature_matrix.h5` | `filtered_feature_bc_matrix.h5` |
| coordinates | inside `cells.parquet` | `tissue_positions.csv` |
| image | `morphology.ome.tif` (DAPI, 3D) | `tissue_hires_image.png` (H&E, 6% scale) |
| coordinate-system info | `experiment.xenium` | `scalefactors_json.json` |
| segmentation | `cell_boundaries.parquet` | — (spots are not cells) |
| 10x clusters | `analysis/` | `analysis/` (separate download) |
| transcript coords | `transcripts.parquet` (opt-in) | — |

Two rules do most of the work:

1. **Drop duplicate encodings.** 10x ships the same table as `.csv.gz`,
   `.parquet` and `.zarr.zip`; we keep only `.parquet`. On the Xenium mouse
   brain sample this removes ~900 MB with no information loss. Same rule on
   Visium (`.h5` vs the MTX triplet).
2. **Drop human-facing artefacts.** QC overlay JPEGs, HTML reports, and
   Loupe/Explorer-only formats carry no data we cannot recompute.

Note that the 10x `analysis/` clusters *are* kept, even though they are
clusters rather than cell types — they are occasionally needed, and the
folder is only ~12 MB.

## Review history

Decisions confirmed with Yaqi on 2026-09-30:

- dropping duplicate encodings — confirmed
- standardised naming — confirmed
- `analysis/` clusters — **keep** (changed from dropping them)
- Xenium image — **keep the full 2.2 GB 3D stack**, the z-axis is sometimes
  needed (changed from keeping only the MIP). The MIP is kept alongside it
  since it is cheap and most 2D work wants it.
- `transcripts.parquet` — not needed, no re-segmentation planned. Left
  behind `--with-transcripts` rather than deleted, in case expression ever
  has to be re-assigned from raw transcript coordinates.

## Open question

**Visium full-resolution H&E.** `tissue_hires_image.png` is only ~5.6% of
full resolution — a 55 µm spot is about 14 px across, too small for image
patches or nuclear segmentation. The real full-resolution microscope image
is a Space Ranger *input*, not an output, so it is not in the downloaded
folder. `image_fullres.tif` is in the keep-list as optional and is picked
up automatically if the file is placed next to the matrix. Some datasets
genuinely have no original image.

## Tests

```bash
pip install -e ".[dev]"
python -m pytest tests/
```

21 tests, running against synthetic folders that mirror the real 10x
layouts (`tests/make_fixtures.py`), so no data download is needed.
