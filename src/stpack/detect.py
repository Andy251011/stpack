"""Work out which platform a raw sample folder came from."""

from pathlib import Path

# Files that only ever appear in one platform's output. Several per
# platform on purpose: detection should still work if one file happens to
# be absent from a particular run.
SIGNATURES = {
    "xenium": [
        "experiment.xenium",
        "cell_feature_matrix.h5",
        "cells.parquet",
    ],
    "visium": [
        "spatial/scalefactors_json.json",
        "spatial/tissue_positions.csv",
        "spatial/tissue_positions_list.csv",
        "spatial/tissue_hires_image.png",
    ],
}


def detect_platform(sample_dir: Path) -> str:
    """Return 'xenium' or 'visium'.

    Raises ValueError if the folder matches nothing, or matches more than
    one platform (which would mean something is wrong with the folder).
    """
    sample_dir = Path(sample_dir)
    if not sample_dir.is_dir():
        raise ValueError(f"not a directory: {sample_dir}")

    matches = []
    for platform, signature_files in SIGNATURES.items():
        if any((sample_dir / f).exists() for f in signature_files):
            matches.append(platform)

    if not matches:
        raise ValueError(
            f"could not identify platform for {sample_dir}. Looked for "
            f"{SIGNATURES}. Pass --platform explicitly to override."
        )
    if len(matches) > 1:
        raise ValueError(
            f"{sample_dir} looks like more than one platform: {matches}"
        )
    return matches[0]
