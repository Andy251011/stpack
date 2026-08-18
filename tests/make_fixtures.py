"""Create fake sample folders that mirror the real 10x layouts.

File names and nesting match what we saw in:
  - Xenium_V1_FF_Mouse_Brain_Coronal_Subset_CTX_HP
  - CytAssist_FFPE_Human_Lung_Squamous_Cell_Carcinoma
Contents are junk bytes -- we are testing file selection, not data.
"""

from pathlib import Path

XENIUM_FILES = [
    "analysis_summary.html",
    "analysis.zarr.zip",
    "cell_boundaries.csv.gz",
    "cell_boundaries.parquet",
    "cell_feature_matrix.h5",
    "cell_feature_matrix.zarr.zip",
    "cells.csv.gz",
    "cells.parquet",
    "cells.zarr.zip",
    "experiment.xenium",
    "gene_panel.json",
    "metrics_summary.csv",
    "morphology_focus.ome.tif",
    "morphology_mip.ome.tif",
    "morphology.ome.tif",
    "nucleus_boundaries.csv.gz",
    "nucleus_boundaries.parquet",
    "transcripts.csv.gz",
    "transcripts.parquet",
    "transcripts.zarr.zip",
    "cell_feature_matrix/barcodes.tsv.gz",
    "cell_feature_matrix/features.tsv.gz",
    "cell_feature_matrix/matrix.mtx.gz",
    "analysis/clustering/gene_expression_graphclust/clusters.csv",
    "analysis/clustering/gene_expression_kmeans_2_clusters/clusters.csv",
    "analysis/pca/gene_expression_10_components/projection.csv",
    "analysis/umap/gene_expression_2_components/projection.csv",
]

VISIUM_FILES = [
    "CytAssist_FFPE_Human_Lung_Squamous_Cell_Carcinoma_filtered_feature_bc_matrix.h5",
    "CytAssist_FFPE_Human_Lung_Squamous_Cell_Carcinoma_metrics_summary.csv",
    "spatial/aligned_fiducials.jpg",
    "spatial/aligned_tissue_image.jpg",
    "spatial/cytassist_image.tiff",
    "spatial/detected_tissue_image.jpg",
    "spatial/scalefactors_json.json",
    "spatial/spatial_enrichment.csv",
    "spatial/tissue_hires_image.png",
    "spatial/tissue_lowres_image.png",
    "spatial/tissue_positions.csv",
]

# Older Space Ranger named this differently -- used to test the fallback.
VISIUM_OLD_FILES = [
    "filtered_feature_bc_matrix.h5",
    "spatial/scalefactors_json.json",
    "spatial/tissue_positions_list.csv",
    "spatial/tissue_hires_image.png",
]


def make(root: Path, files: list[str]) -> Path:
    for rel in files:
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"x" * 128)
    return root


def build_all(base: Path) -> dict[str, Path]:
    return {
        "xenium": make(base / "xenium_mouse_brain", XENIUM_FILES),
        "visium": make(base / "visium_lung", VISIUM_FILES),
        "visium_old": make(base / "visium_old_spaceranger", VISIUM_OLD_FILES),
    }


if __name__ == "__main__":
    import sys

    base = Path(sys.argv[1] if len(sys.argv) > 1 else "./fixtures")
    for name, path in build_all(base).items():
        print(f"{name}: {path}")
