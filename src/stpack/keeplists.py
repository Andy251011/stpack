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
"""

from dataclasses import dataclass, field


@dataclass
class FileSpec:
    """One file we want to keep."""

    standard_name: str  # what we call it in the output archive
    candidates: list[str]  # possible paths inside the raw sample folder
    required: bool = True
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
            ["morphology_mip.ome.tif", "morphology_focus.ome.tif"],
            note="2D DAPI morphology image (MIP preferred over the 3D stack)",
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
            "transcripts.parquet",
            ["transcripts.parquet"],
            required=False,
            note="per-transcript coordinates; large, only needed for "
            "re-segmentation. Enable with --with-transcripts.",
        ),
    ],
    dropped={
        "*.csv.gz": "duplicate of the .parquet files (same content, larger)",
        "*.zarr.zip": "duplicate, for the Xenium Explorer desktop app only",
        "cell_feature_matrix/": "MTX-format duplicate of cell_feature_matrix.h5",
        "morphology.ome.tif": "full 3D z-stack (~2 GB); the MIP projection "
        "carries what downstream analysis needs",
        "morphology_focus.ome.tif": "alternate 2D morphology image; the MIP "
        "projection is the preferred standard image",
        "analysis/": "10x kmeans/graph clusters -- these are clusters, not "
        "cell types; we predict cell types ourselves",
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
            "image_fullres.tif",
            [
                "image_fullres.tif",
                "*_image.tif",
                "*_image.tiff",
                "*_tissue_image.btf",
            ],
            required=False,
            note="original full-resolution microscope H&E. Not part of "
            "Space Ranger output -- must be supplied separately. Required "
            "if per-spot image patches are ever wanted.",
        ),
    ],
    dropped={
        "spatial/aligned_fiducials.jpg": "QC overlay for humans",
        "spatial/aligned_tissue_image.jpg": "QC overlay for humans",
        "spatial/detected_tissue_image.jpg": "QC overlay for humans",
        "spatial/spatial_enrichment.csv": "downstream Moran's I result, "
        "not raw data",
        "*_spatial.tar.gz": "download container for the extracted spatial/ files",
        "raw_feature_bc_matrix*": "includes off-tissue spots; filtered "
        "matrix is what analysis uses",
        "*.cloupe": "Loupe Browser proprietary format",
        "*.bam": "read alignments, only needed to re-run Space Ranger",
        "*.bam.bai": "read alignment index, only needed with the BAM file",
        "molecule_info.h5": "sequencing-level intermediate",
        "analysis/": "Space Ranger clusters -- clusters, not cell types",
        "web_summary.html": "human-readable report, no data",
    },
)

PLATFORMS: dict[str, PlatformSpec] = {
    "xenium": XENIUM,
    "visium": VISIUM,
}

# Optional extras -- off by default because of size.
# transcripts.parquet is ~174 MB for a small Xenium sample.
OPTIONAL_BY_DEFAULT = {"transcripts.parquet"}
