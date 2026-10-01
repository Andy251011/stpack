import json
import tarfile

import pytest

from make_fixtures import build_all
from stpack import detect_platform, package_sample


@pytest.fixture
def samples(tmp_path):
    return build_all(tmp_path / "raw")


def names(manifest) -> set[str]:
    return {f["name"] for f in manifest["files"]}


def originals(manifest) -> set[str]:
    return {f["original_name"] for f in manifest["files"]}


# --- platform detection ------------------------------------------------


def test_detects_xenium(samples):
    assert detect_platform(samples["xenium"]) == "xenium"


def test_detects_visium(samples):
    assert detect_platform(samples["visium"]) == "visium"


def test_unknown_folder_raises(tmp_path):
    empty = tmp_path / "nothing"
    empty.mkdir()
    with pytest.raises(ValueError):
        detect_platform(empty)


# --- Yaqi's reviewed decisions -----------------------------------------


def test_keeps_full_3d_image_not_the_projection(samples, tmp_path):
    """Reviewed 2026-09-30: the z-axis is sometimes needed."""
    m = package_sample(samples["xenium"], tmp_path / "out", dry_run=True)
    image = next(f for f in m["files"] if f["name"] == "image.ome.tif")
    assert image["original_name"] == "morphology.ome.tif"


def test_also_keeps_the_mip_alongside_it(samples, tmp_path):
    m = package_sample(samples["xenium"], tmp_path / "out", dry_run=True)
    mip = next(f for f in m["files"] if f["name"] == "image_mip.ome.tif")
    assert mip["original_name"] == "morphology_mip.ome.tif"


def test_keeps_analysis_folder(samples, tmp_path):
    """Reviewed 2026-09-30: the 10x clusters are sometimes needed."""
    m = package_sample(samples["xenium"], tmp_path / "out", dry_run=True)
    analysis = next(f for f in m["files"] if f["name"] == "analysis")
    assert analysis["kind"] == "dir"
    assert analysis["size_bytes"] > 0


def test_transcripts_excluded_by_default(samples, tmp_path):
    m = package_sample(samples["xenium"], tmp_path / "out", dry_run=True)
    assert "transcripts.parquet" not in names(m)


def test_transcripts_included_on_request(samples, tmp_path):
    m = package_sample(
        samples["xenium"],
        tmp_path / "out",
        include_optional={"transcripts.parquet"},
        dry_run=True,
    )
    assert "transcripts.parquet" in names(m)


def test_drops_duplicate_formats(samples, tmp_path):
    m = package_sample(samples["xenium"], tmp_path / "out", dry_run=True)
    assert not any(
        n.endswith((".csv.gz", ".zarr.zip")) for n in originals(m)
    )


def test_drops_focus_image(samples, tmp_path):
    m = package_sample(samples["xenium"], tmp_path / "out", dry_run=True)
    assert "morphology_focus.ome.tif" not in originals(m)


def test_visium_drops_qc_overlays(samples, tmp_path):
    m = package_sample(samples["visium"], tmp_path / "out", dry_run=True)
    assert not any(n.endswith(".jpg") for n in originals(m))


# --- version tolerance -------------------------------------------------


def test_old_spaceranger_naming_fallback(samples, tmp_path):
    """tissue_positions_list.csv is the pre-2.0 name for the same file."""
    m = package_sample(samples["visium_old"], tmp_path / "out", dry_run=True)
    pos = next(f for f in m["files"] if f["name"] == "tissue_positions.csv")
    assert pos["original_name"] == "tissue_positions_list.csv"


def test_visium_fullres_image_picked_up_when_present(samples, tmp_path):
    m = package_sample(samples["visium_extras"], tmp_path / "out",
                       dry_run=True)
    full = next(f for f in m["files"] if f["name"] == "image_fullres.tif")
    assert full["original_name"].endswith("_tissue_image.tif")


def test_visium_fullres_image_reported_missing_when_absent(samples, tmp_path):
    m = package_sample(samples["visium"], tmp_path / "out", dry_run=True)
    assert "image_fullres.tif" in m["missing"]


def test_visium_analysis_folder_optional(samples, tmp_path):
    """Visium clusters ship as a separate download, so absence is fine."""
    without = package_sample(samples["visium"], tmp_path / "a", dry_run=True)
    assert "analysis" in without["missing"]

    with_it = package_sample(
        samples["visium_extras"], tmp_path / "b", dry_run=True
    )
    assert "analysis" in names(with_it)


def test_glob_does_not_match_a_directory_as_a_file(samples, tmp_path):
    """*_image.tif must not accidentally resolve to a folder."""
    (samples["visium"] / "stray_image.tif").mkdir()
    m = package_sample(samples["visium"], tmp_path / "out", dry_run=True)
    assert "image_fullres.tif" in m["missing"]


# --- failure behaviour -------------------------------------------------


def test_missing_required_file_fails_loudly(samples, tmp_path):
    (samples["visium"] / "spatial" / "scalefactors_json.json").unlink()
    with pytest.raises(FileNotFoundError, match="scalefactors"):
        package_sample(samples["visium"], tmp_path / "out", dry_run=True)


def test_does_not_overwrite_by_default(samples, tmp_path):
    out = tmp_path / "out"
    package_sample(samples["visium"], out)
    with pytest.raises(FileExistsError):
        package_sample(samples["visium"], out)
    package_sample(samples["visium"], out, overwrite=True)  # ok


# --- the archive itself ------------------------------------------------


def test_archive_layout_and_manifest(samples, tmp_path):
    out = tmp_path / "out"
    package_sample(samples["visium"], out, sample_id="lung_A1")
    archive = out / "lung_A1.tar.gz"
    assert archive.exists()

    with tarfile.open(archive) as tar:
        members = tar.getnames()
        assert "lung_A1/manifest.json" in members
        assert "lung_A1/expression.h5" in members
        assert "lung_A1/scalefactors.json" in members
        manifest = json.load(tar.extractfile("lung_A1/manifest.json"))

    assert manifest["sample_id"] == "lung_A1"
    assert manifest["platform"] == "visium"
    assert all(len(f["sha256"]) == 64 for f in manifest["files"])


def test_archive_contains_the_analysis_subtree(samples, tmp_path):
    out = tmp_path / "out"
    package_sample(samples["xenium"], out, sample_id="xe")
    with tarfile.open(out / "xe.tar.gz") as tar:
        members = tar.getnames()
    assert (
        "xe/analysis/clustering/gene_expression_graphclust/clusters.csv"
        in members
    )


def test_checksums_are_stable_for_folders(samples, tmp_path):
    """Same folder packaged twice -> same analysis/ checksum."""
    a = package_sample(samples["xenium"], tmp_path / "a", sample_id="x")
    b = package_sample(samples["xenium"], tmp_path / "b", sample_id="x")
    ha = next(f["sha256"] for f in a["files"] if f["name"] == "analysis")
    hb = next(f["sha256"] for f in b["files"] if f["name"] == "analysis")
    assert ha == hb
