"""
Which files to keep from each platform's raw output folder.

This module is the heart of the package: it is a decision table, not code.
Everything else just executes what is written here.

Each entry maps a STANDARD NAME (what the file is called in our output)
to a list of CANDIDATE PATHS (what the vendor might call it). The first
candidate that exists on disk wins -- this is how we absorb differences
between software versions (e.g. tissue_positions.csv vs
tissue_positions_list.csv in older Space Ranger output).

required=True  -> if missing, packaging fails loudly.
required=False -> if missing, we note it in the manifest and move on.

Decisions reviewed by Yaqi 2026-09-30:
  - dropping duplicate encodings: confirmed
  - standardised naming: confirmed
  - analysis/ clusters: KEEP (sometimes needed)      <- changed
  - Xenium image: keep the full 3D stack, z-axis is  <- changed
    sometimes needed
  - transcripts.parquet: not needed, no re-segmentation planned
"""

from dataclasses import dataclass, field


@dataclass
class FileSpec:
    """One file (or folder) we want to keep."""

    standard_name: str  # what we call it in the output archive
    candidates: list[str]  # possible paths inside the raw sample folder
    required: bool = True
    is_dir: bool = False  # copy recursively instead of as a single file
    note: str = ""  # why we keep it (ends up in the manifest)


@dataclass
class PlatformSpec:
    """The keep-list for one platform."""

    name: str
    files: list[FileSpec]
    # Files/folders we deliberately drop. Recorded in the manifest so the
    # decision is documented rather than silent.
    dropped: dict[str, str] = field(default_factory=dict)


XENIUM = PlatformSpec(
    name="xenium",
    files=[
        FileSpec(
            "expression.h5",
            ["cell_feature_matrix.h5"],
            note="cell x gene count matrix",
        ),
        FileSpec(
            "cells.parquet",
            ["cells.parquet"],
            note="per-cell metadata: centroid x/y, area, transcript counts",
        ),
        FileSpec(
            "cell_boundaries.parquet",
            ["cell_boundaries.parquet"],
            required=False,
            note="cell segmentation polygons",
        ),
        FileSpec(
            "nucleus_boundaries.parquet",
            ["nucleus_boundaries.parquet"],
            required=False,
            note="nucleus segmentation polygons",
        ),
        FileSpec(
            "image.ome.tif",
            ["morphology.ome.tif"],
            note="full 3D DAPI morphology z-stack (~2 GB). Kept in full "
            "because the z-axis information is sometimes needed.",
        ),
        FileSpec(
            "image_mip.ome.tif",
            ["morphology_mip.ome.tif"],
            required=False,
            note="2D maximum-intensity projection of the same stack "
            "(~207 MB). Kept alongside the 3D image because most 2D "
            "analysis wants it and it is cheap next to 2 GB.",
        ),
        FileSpec(
            "gene_panel.json",
            ["gene_panel.json"],
            note="which genes this panel measures; needed to compare samples",
        ),
        FileSpec(
            "experiment.xenium",
            ["experiment.xenium"],
            note="run metadata incl. pixel size; without it image and coords "
            "cannot be aligned",
        ),
        FileSpec(
            "metrics_summary.csv",
            ["metrics_summary.csv"],
            required=False,
            note="QC metrics",
        ),
        FileSpec(
            "analysis",
            ["analysis"],
            required=False,
            is_dir=True,
            note="10x on-instrument clustering, diffexp, PCA and UMAP. "
            "These are clusters, not cell types, but the information is "
            "sometimes needed. ~12 MB.",
        ),
        FileSpec(
            "transcripts.parquet",
            ["transcripts.parquet"],
            required=False,
            note="per-transcript coordinates (~174 MB). Off by default: "
            "no re-segmentation planned. Still reachable via "
            "--with-transcripts if expression ever has to be re-assigned "
            "from raw transcripts.",
        ),
    ],
    dropped={
        "*.csv.gz": "duplicate of the .parquet files (same content, larger)",
        "*.zarr.zip": "duplicate, for the Xenium Explorer desktop app only",
        "cell_feature_matrix/": "MTX-format duplicate of cell_feature_matrix.h5",
        "morphology_focus.ome.tif": "per-pixel best-focus composite; the 3D "
        "stack and its MIP cover what we need",
        "analysis_summary.html": "human-readable report, no data",
    },
)

VISIUM = PlatformSpec(
    name="visium",
    files=[
        FileSpec(
            "expression.h5",
            [
                "filtered_feature_bc_matrix.h5",
                "*_filtered_feature_bc_matrix.h5",
            ],
            note="spot x gene count matrix (tissue-covered spots only)",
        ),
        FileSpec(
            "tissue_positions.csv",
            [
                "spatial/tissue_positions.csv",
                "spatial/tissue_positions_list.csv",
            ],
            note="per-spot barcode, array row/col, full-res pixel coords",
        ),
        FileSpec(
            "scalefactors.json",
            ["spatial/scalefactors_json.json"],
            note="pixel scaling between full-res coords and the stored "
            "images; tiny but the data is unusable without it",
        ),
        FileSpec(
            "image_hires.png",
            ["spatial/tissue_hires_image.png"],
            note="H&E downsampled to ~6% of full resolution",
        ),
        FileSpec(
            "image_lowres.png",
            ["spatial/tissue_lowres_image.png"],
            required=False,
            note="H&E thumbnail, ~2% scale; kept because it is tiny",
        ),
        FileSpec(
            "cytassist_image.tiff",
            ["spatial/cytassist_image.tiff"],
            required=False,
            note="CytAssist instrument image used for alignment; "
            "CytAssist runs only",
        ),
        FileSpec(
            "metrics_summary.csv",
            ["metrics_summary.csv", "*_metrics_summary.csv"],
            required=False,
            note="QC metrics",
        ),
        FileSpec(
            "analysis",
            ["analysis"],
            required=False,
            is_dir=True,
            note="Space Ranger clustering / diffexp / PCA / UMAP. Ships as "
            "a separate 'Clustering analysis' download, so it is only "
            "picked up if it has been extracted next to the matrix.",
        ),
        FileSpec(
            "image_fullres.tif",
            [
                "image_fullres.tif",
                "*_image.tif",
                "*_image.tiff",
                "*_tissue_image.btf",
                "*_image.btf",
            ],
            required=False,
            note="original full-resolution microscope H&E. Not part of "
            "Space Ranger output -- must be downloaded separately from the "
            "dataset's Input files. REQUIRED for CellViT segmentation and "
            "for per-spot image patches.",
        ),
    ],
    dropped={
        "spatial/aligned_fiducials.jpg": "QC overlay for humans",
        "spatial/aligned_tissue_image.jpg": "QC overlay for humans",
        "spatial/detected_tissue_image.jpg": "QC overlay for humans",
        "spatial/spatial_enrichment.csv": "downstream Moran's I result, "
        "not raw data",
        "raw_feature_bc_matrix*": "includes off-tissue spots; filtered "
        "matrix is what analysis uses",
        "*.cloupe": "Loupe Browser proprietary format",
        "*.bam / *.bam.bai": "read alignments, only needed to re-run "
        "Space Ranger",
        "molecule_info.h5": "sequencing-level intermediate",
        "web_summary.html": "human-readable report, no data",
    },
)

PLATFORMS: dict[str, PlatformSpec] = {
    "xenium": XENIUM,
    "visium": VISIUM,
}

# Optional extras -- off by default because of size.
OPTIONAL_BY_DEFAULT = {"transcripts.parquet"}
