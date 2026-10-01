"""Turn one raw sample folder into one standardised .tar.gz archive."""

from __future__ import annotations

import hashlib
import json
import shutil
import tarfile
import tempfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from .detect import detect_platform
from .keeplists import OPTIONAL_BY_DEFAULT, PLATFORMS, FileSpec, PlatformSpec

SCHEMA_VERSION = "0.2"


@dataclass
class ResolvedFile:
    """A keep-list entry that we actually found on disk."""

    standard_name: str
    source_path: Path
    size_bytes: int
    note: str
    is_dir: bool = False


def _find(sample_dir: Path, spec: FileSpec) -> Path | None:
    """First candidate path that exists. Supports simple * globs."""
    for candidate in spec.candidates:
        if "*" in candidate:
            hits = sorted(sample_dir.glob(candidate))
            hits = [h for h in hits if h.is_dir() == spec.is_dir]
            if hits:
                return hits[0]
        else:
            path = sample_dir / candidate
            if path.exists() and path.is_dir() == spec.is_dir:
                return path
    return None


def _dir_size(path: Path) -> int:
    return sum(f.stat().st_size for f in path.rglob("*") if f.is_file())


def _sha256(path: Path, chunk_size: int = 1024 * 1024) -> str:
    """Checksum, read in chunks so we never load a 2 GB image into RAM."""
    digest = hashlib.sha256()
    with open(path, "rb") as fh:
        while chunk := fh.read(chunk_size):
            digest.update(chunk)
    return digest.hexdigest()


def _sha256_dir(path: Path) -> str:
    """Checksum of a folder: hash each file's relative path and content, in
    sorted order, so the result does not depend on filesystem ordering."""
    digest = hashlib.sha256()
    for f in sorted(p for p in path.rglob("*") if p.is_file()):
        digest.update(str(f.relative_to(path)).encode())
        digest.update(_sha256(f).encode())
    return digest.hexdigest()


def resolve_files(
    sample_dir: Path,
    spec: PlatformSpec,
    include_optional: set[str] | None = None,
) -> tuple[list[ResolvedFile], list[str]]:
    """Match the keep-list against what is actually in the folder.

    Returns (found, missing). `missing` only lists files we wanted but did
    not find; required files that are missing are reported by the caller.
    """
    include_optional = include_optional or set()
    found: list[ResolvedFile] = []
    missing: list[str] = []

    for file_spec in spec.files:
        # Skip heavyweight extras unless explicitly asked for.
        if (
            file_spec.standard_name in OPTIONAL_BY_DEFAULT
            and file_spec.standard_name not in include_optional
        ):
            continue

        path = _find(sample_dir, file_spec)
        if path is None:
            missing.append(file_spec.standard_name)
            continue

        size = _dir_size(path) if file_spec.is_dir else path.stat().st_size
        found.append(
            ResolvedFile(
                standard_name=file_spec.standard_name,
                source_path=path,
                size_bytes=size,
                note=file_spec.note,
                is_dir=file_spec.is_dir,
            )
        )
    return found, missing


def required_names(spec: PlatformSpec) -> set[str]:
    return {f.standard_name for f in spec.files if f.required}


def build_manifest(
    sample_id: str,
    platform: str,
    sample_dir: Path,
    found: list[ResolvedFile],
    missing: list[str],
    checksums: dict[str, str],
) -> dict:
    """Everything a future reader needs to know about this archive."""
    return {
        "schema_version": SCHEMA_VERSION,
        "sample_id": sample_id,
        "platform": platform,
        "created_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "source_dir": str(sample_dir.resolve()),
        "files": [
            {
                "name": f.standard_name,
                "original_name": f.source_path.name,
                "kind": "dir" if f.is_dir else "file",
                "size_bytes": f.size_bytes,
                "sha256": checksums[f.standard_name],
                "note": f.note,
            }
            for f in found
        ],
        "missing": missing,
        "dropped_rules": PLATFORMS[platform].dropped,
    }


def package_sample(
    sample_dir: str | Path,
    out_dir: str | Path,
    sample_id: str | None = None,
    platform: str | None = None,
    include_optional: set[str] | None = None,
    dry_run: bool = False,
    overwrite: bool = False,
) -> dict:
    """Package one sample.

    Returns the manifest dict. With dry_run=True nothing is written --
    useful for checking a folder before committing to a long copy.
    """
    sample_dir = Path(sample_dir)
    out_dir = Path(out_dir)
    sample_id = sample_id or sample_dir.resolve().name
    platform = platform or detect_platform(sample_dir)

    if platform not in PLATFORMS:
        raise ValueError(f"unknown platform {platform!r}")
    spec = PLATFORMS[platform]

    found, missing = resolve_files(sample_dir, spec, include_optional)

    # Fail loudly if something essential is absent -- a silently incomplete
    # archive is worse than no archive.
    missing_required = sorted(set(missing) & required_names(spec))
    if missing_required:
        raise FileNotFoundError(
            f"{sample_id}: required file(s) not found: "
            f"{', '.join(missing_required)}"
        )

    if dry_run:
        return build_manifest(
            sample_id,
            platform,
            sample_dir,
            found,
            missing,
            {f.standard_name: "(dry-run)" for f in found},
        )

    out_dir.mkdir(parents=True, exist_ok=True)
    archive_path = out_dir / f"{sample_id}.tar.gz"
    if archive_path.exists() and not overwrite:
        raise FileExistsError(f"{archive_path} exists (use overwrite=True)")

    # Stage into a temp dir under the output location, then tar it. Staging
    # means the archive only ever contains renamed, verified files.
    with tempfile.TemporaryDirectory(dir=out_dir) as tmp:
        staging = Path(tmp) / sample_id
        staging.mkdir()

        checksums: dict[str, str] = {}
        for f in found:
            dest = staging / f.standard_name
            if f.is_dir:
                shutil.copytree(f.source_path, dest)
                checksums[f.standard_name] = _sha256_dir(dest)
            else:
                shutil.copy2(f.source_path, dest)
                checksums[f.standard_name] = _sha256(dest)

        manifest = build_manifest(
            sample_id, platform, sample_dir, found, missing, checksums
        )
        (staging / "manifest.json").write_text(json.dumps(manifest, indent=2))

        with tarfile.open(archive_path, "w:gz") as tar:
            tar.add(staging, arcname=sample_id)

    return manifest
