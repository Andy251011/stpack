# stpack

Turns one raw spatial transcriptomics sample folder into one standardised
`.tar.gz` containing only the files we actually need, plus a manifest
recording what was kept, what was dropped, and why.

Currently supports **Xenium** and **Visium** (including CytAssist).

## Install

```bash
git clone <repo> && cd stpack
pip install -e .
```

No dependencies beyond the standard library.

## Use

```bash
# See what would be kept, without writing anything
stpack /path/to/xenium_mouse_brain --dry-run

# Package it
stpack /path/to/xenium_mouse_brain -o ./packaged

# Xenium: also keep transcripts.parquet (large, off by default)
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
lung_A1.tar.gz
└── lung_A1/
    ├── expression.h5
    ├── tissue_positions.csv
    ├── scalefactors.json
    ├── image_hires.png
    ├── metrics_summary.csv
    └── manifest.json
```

File names are standardised across platforms, so `expression.h5` means the
same thing whether the sample came from Xenium or Visium. The manifest
records the original vendor filename, size, and a SHA-256 checksum for
each file.

## What gets kept

The full decision table lives in `src/stpack/keeplists.py` — it is meant
to be read and argued with, not buried. Summary:

| Concept | Xenium | Visium |
|---|---|---|
| expression matrix | `cell_feature_matrix.h5` | `filtered_feature_bc_matrix.h5` |
| coordinates | inside `cells.parquet` | `tissue_positions.csv` |
| image | `morphology_mip.ome.tif` (DAPI) | `tissue_hires_image.png` (H&E) |
| coordinate-system info | `experiment.xenium` | `scalefactors_json.json` |
| segmentation | `cell_boundaries.parquet` | — (spots are not cells) |
| transcript coords | `transcripts.parquet` (optional) | — |

Two rules do most of the work:

1. **Drop duplicate encodings.** 10x ships the same table as `.csv.gz`,
   `.parquet` and `.zarr.zip`; we keep only `.parquet`. On the Xenium
   mouse brain sample this alone removes ~900 MB with no information loss.
   The same rule applies on Visium (`.h5` vs the MTX triplet).
2. **Drop derived results.** `analysis/` clusters, `spatial_enrichment.csv`,
   QC overlay JPEGs and HTML reports are outputs of someone else's
   analysis, not raw data. In particular the 10x clusters are *clusters*,
   not cell types.

## Open questions

Marked here rather than silently decided:

1. **Xenium image.** We keep `morphology_mip.ome.tif` (~207 MB, 2D
   projection) over `morphology.ome.tif` (~2 GB, full 3D z-stack).
   Confirm the 3D stack is not needed.
2. **`transcripts.parquet`** (~174 MB). The only route to re-segmentation,
   dead weight otherwise. Currently opt-in via `--with-transcripts`.
3. **Visium full-resolution H&E.** `tissue_hires_image.png` is only ~5.6%
   of full resolution — a 55 µm spot is about 14 px across, too small for
   image patches. The real full-resolution image is a Space Ranger *input*,
   not an output, so it must be supplied separately. `image_fullres.tif`
   is in the keep-list as optional and will be picked up if present.
4. **Sample granularity.** One archive per tissue section. If one donor
   has several sections, or the same section is run on both platforms,
   confirm they stay separate.

## Tests

```bash
pip install -e ".[dev]"
python -m pytest tests/
```

Tests run against synthetic folders that mirror the real 10x layouts
(`tests/make_fixtures.py`), so they need no data download.
