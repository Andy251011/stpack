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


def _find(sample_dir: Path, spec: FileSpec) -> Path | None:
    """First candidate path that exists. Supports simple * globs."""
    for candidate in spec.candidates:
        if "*" in candidate:
            hits = sorted(sample_dir.glob(candidate))
            if hits:
                return hits[0]
        else:
            path = sample_dir / candidate
            if path.exists():
                return path
    return None


def _sha256(path: Path, chunk_size: int = 1024 * 1024) -> str:
    """Checksum, read in chunks so we never load a 2 GB image into RAM."""
    digest = hashlib.sha256()
    with open(path, "rb") as fh:
        while chunk := fh.read(chunk_size):
            digest.update(chunk)
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

        found.append(
            ResolvedFile(
                standard_name=file_spec.standard_name,
                source_path=path,
                size_bytes=path.stat().st_size,
                note=file_spec.note,
            )
        )
    return found, missing


def required_names(spec: PlatformSpec) -> set[str]:
    return {f.standard_name for f in spec.files if f.required}


def _validate_sample_id(sample_id: str) -> str:
    """Require a single safe path component for archive and folder names."""
    if (
        not sample_id
        or sample_id in {".", ".."}
        or "/" in sample_id
        or "\\" in sample_id
    ):
        raise ValueError(
            "sample_id must be a non-empty name without path separators"
        )
    return sample_id


def inventory_dropped_files(
    sample_dir: Path,
    spec: PlatformSpec,
    found: list[ResolvedFile],
    include_optional: set[str] | None = None,
) -> list[dict[str, str]]:
    """List paths present in the sample but deliberately not packaged."""
    include_optional = include_optional or set()
    kept_paths = {
        f.source_path.relative_to(sample_dir).as_posix() for f in found
    }
    dropped: dict[str, str] = {}
    dropped_dirs: set[Path] = set()

    def record(path: Path, reason: str) -> None:
        relative = path.relative_to(sample_dir).as_posix()
        if relative in kept_paths:
            return
        if path.is_dir() and not path.is_symlink():
            relative += "/"
            dropped_dirs.add(path)
        dropped.setdefault(relative, reason)

    # Optional heavyweight files are intentionally omitted unless requested.
    for file_spec in spec.files:
        if (
            file_spec.standard_name in OPTIONAL_BY_DEFAULT
            and file_spec.standard_name not in include_optional
        ):
            path = _find(sample_dir, file_spec)
            if path is not None:
                record(path, f"optional by default; {file_spec.note}")

    # Convert the documented drop rules into an inventory of actual matches.
    for pattern, reason in spec.dropped.items():
        for path in sorted(sample_dir.glob(pattern.rstrip("/"))):
            record(path, reason)

    # Anything else is still omitted, so record it instead of hiding it.
    for path in sorted(sample_dir.rglob("*")):
        if any(parent in dropped_dirs for parent in path.parents):
            continue
        relative = path.relative_to(sample_dir).as_posix()
        if relative in kept_paths or relative in dropped:
            continue
        if path.is_dir() and not path.is_symlink():
            continue
        record(path, "not selected by the keep-list")

    return [
        {"path": path, "reason": reason}
        for path, reason in sorted(dropped.items())
    ]


def build_manifest(
    sample_id: str,
    platform: str,
    sample_dir: Path,
    found: list[ResolvedFile],
    missing: list[str],
    checksums: dict[str, str],
    dropped: list[dict[str, str]],
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
                "size_bytes": f.size_bytes,
                "sha256": checksums[f.standard_name],
                "note": f.note,
            }
            for f in found
        ],
        "missing": missing,
        "dropped": dropped,
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
    if sample_id is None:
        sample_id = sample_dir.resolve().name
    sample_id = _validate_sample_id(sample_id)
    platform = platform or detect_platform(sample_dir)

    if platform not in PLATFORMS:
        raise ValueError(f"unknown platform {platform!r}")
    spec = PLATFORMS[platform]

    found, missing = resolve_files(sample_dir, spec, include_optional)
    dropped = inventory_dropped_files(
        sample_dir, spec, found, include_optional
    )

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
            dropped,
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
            shutil.copy2(f.source_path, dest)
            checksums[f.standard_name] = _sha256(dest)

        manifest = build_manifest(
            sample_id,
            platform,
            sample_dir,
            found,
            missing,
            checksums,
            dropped,
        )
        (staging / "manifest.json").write_text(json.dumps(manifest, indent=2))

        with tarfile.open(archive_path, "w:gz") as tar:
            tar.add(staging, arcname=sample_id)

    return manifest
