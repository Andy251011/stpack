import json
import tarfile

import pytest

from make_fixtures import build_all
from stpack import detect_platform, package_sample


@pytest.fixture
def samples(tmp_path):
    return build_all(tmp_path / "raw")


def test_detects_xenium(samples):
    assert detect_platform(samples["xenium"]) == "xenium"


def test_detects_visium(samples):
    assert detect_platform(samples["visium"]) == "visium"


def test_unknown_folder_raises(tmp_path):
    empty = tmp_path / "nothing"
    empty.mkdir()
    with pytest.raises(ValueError):
        detect_platform(empty)


def test_prefers_mip_over_focus_image(samples, tmp_path):
    m = package_sample(samples["xenium"], tmp_path / "out", dry_run=True)
    image = next(f for f in m["files"] if f["name"] == "image.ome.tif")
    assert image["original_name"] == "morphology_mip.ome.tif"


def test_transcripts_excluded_by_default(samples, tmp_path):
    m = package_sample(samples["xenium"], tmp_path / "out", dry_run=True)
    assert "transcripts.parquet" not in {f["name"] for f in m["files"]}


def test_transcripts_included_on_request(samples, tmp_path):
    m = package_sample(
        samples["xenium"],
        tmp_path / "out",
        include_optional={"transcripts.parquet"},
        dry_run=True,
    )
    assert "transcripts.parquet" in {f["name"] for f in m["files"]}
    assert "transcripts.parquet" not in {f["path"] for f in m["dropped"]}


def test_manifest_records_actual_dropped_paths(samples, tmp_path):
    m = package_sample(samples["xenium"], tmp_path / "out", dry_run=True)
    dropped = {item["path"]: item["reason"] for item in m["dropped"]}

    assert "transcripts.parquet" in dropped
    assert "optional by default" in dropped["transcripts.parquet"]
    assert "cells.csv.gz" in dropped
    assert "analysis/" in dropped
    assert "preferred standard image" in dropped["morphology_focus.ome.tif"]
    assert "cells.parquet" not in dropped


def test_manifest_records_unmatched_files(samples, tmp_path):
    extra = samples["visium"] / "unexpected.txt"
    extra.write_text("not covered by a keep or drop rule")

    m = package_sample(samples["visium"], tmp_path / "out", dry_run=True)
    dropped = {item["path"]: item["reason"] for item in m["dropped"]}

    assert dropped["unexpected.txt"] == "not selected by the keep-list"


def test_drops_duplicate_formats(samples, tmp_path):
    m = package_sample(samples["xenium"], tmp_path / "out", dry_run=True)
    originals = {f["original_name"] for f in m["files"]}
    assert not any(n.endswith((".csv.gz", ".zarr.zip")) for n in originals)


def test_old_spaceranger_naming_fallback(samples, tmp_path):
    """tissue_positions_list.csv is the pre-2.0 name for the same file."""
    m = package_sample(samples["visium_old"], tmp_path / "out", dry_run=True)
    pos = next(f for f in m["files"] if f["name"] == "tissue_positions.csv")
    assert pos["original_name"] == "tissue_positions_list.csv"


def test_missing_required_file_fails_loudly(samples, tmp_path):
    (samples["visium"] / "spatial" / "scalefactors_json.json").unlink()
    with pytest.raises(FileNotFoundError, match="scalefactors"):
        package_sample(samples["visium"], tmp_path / "out", dry_run=True)


def test_archive_layout_and_manifest(samples, tmp_path):
    out = tmp_path / "out"
    package_sample(samples["visium"], out, sample_id="lung_A1")
    archive = out / "lung_A1.tar.gz"
    assert archive.exists()

    with tarfile.open(archive) as tar:
        names = tar.getnames()
        assert "lung_A1/manifest.json" in names
        assert "lung_A1/expression.h5" in names
        assert "lung_A1/scalefactors.json" in names
        manifest = json.load(tar.extractfile("lung_A1/manifest.json"))

    assert manifest["sample_id"] == "lung_A1"
    assert manifest["platform"] == "visium"
    assert all(len(f["sha256"]) == 64 for f in manifest["files"])
    assert "spatial/aligned_fiducials.jpg" in {
        item["path"] for item in manifest["dropped"]
    }


def test_does_not_overwrite_by_default(samples, tmp_path):
    out = tmp_path / "out"
    package_sample(samples["visium"], out)
    with pytest.raises(FileExistsError):
        package_sample(samples["visium"], out)
    package_sample(samples["visium"], out, overwrite=True)  # ok


@pytest.mark.parametrize(
    "sample_id",
    [
        "",
        ".",
        "..",
        "../escaped",
        "nested/sample",
        r"nested\sample",
        "/tmp/escaped",
    ],
)
def test_rejects_unsafe_sample_id(samples, tmp_path, sample_id):
    with pytest.raises(ValueError, match="sample_id"):
        package_sample(samples["visium"], tmp_path / "out", sample_id=sample_id)
