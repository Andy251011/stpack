"""Command-line interface: stpack <sample_dir> -o <out_dir>"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .detect import detect_platform
from .keeplists import PLATFORMS
from .package import package_sample


def _human(n: int) -> str:
    size = float(n)
    for unit in ("B", "KB", "MB", "GB"):
        if size < 1024 or unit == "GB":
            return f"{size:.1f} {unit}"
        size /= 1024
    return f"{size:.1f} GB"


def _print_summary(manifest: dict, dry_run: bool) -> None:
    total = sum(f["size_bytes"] for f in manifest["files"])
    header = "DRY RUN -- nothing written" if dry_run else "packaged"
    print(f"\n{manifest['sample_id']}  [{manifest['platform']}]  {header}")
    print(f"  {len(manifest['files'])} files, {_human(total)} total\n")
    for f in manifest["files"]:
        print(f"    {f['name']:<28} {_human(f['size_bytes']):>10}"
              f"   <- {f['original_name']}")
    if manifest["missing"]:
        print(f"\n  not found (optional): {', '.join(manifest['missing'])}")
    print()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="stpack",
        description="Package a raw spatial transcriptomics sample folder "
        "into a standardised archive.",
    )
    parser.add_argument("sample_dir", help="raw sample folder")
    parser.add_argument("-o", "--out-dir", default="./packaged",
                        help="where to write the .tar.gz (default: ./packaged)")
    parser.add_argument("--sample-id",
                        help="name for the archive (default: folder name)")
    parser.add_argument("--platform", choices=sorted(PLATFORMS),
                        help="skip auto-detection")
    parser.add_argument("--with-transcripts", action="store_true",
                        help="Xenium only: also keep transcripts.parquet "
                             "(large; needed for re-segmentation)")
    parser.add_argument("--dry-run", action="store_true",
                        help="show what would be kept, write nothing")
    parser.add_argument("--overwrite", action="store_true")
    parser.add_argument("--json", action="store_true",
                        help="print the manifest as JSON instead")
    args = parser.parse_args(argv)

    optional = {"transcripts.parquet"} if args.with_transcripts else set()

    try:
        manifest = package_sample(
            sample_dir=args.sample_dir,
            out_dir=args.out_dir,
            sample_id=args.sample_id,
            platform=args.platform,
            include_optional=optional,
            dry_run=args.dry_run,
            overwrite=args.overwrite,
        )
    except (ValueError, FileNotFoundError, FileExistsError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    if args.json:
        print(json.dumps(manifest, indent=2))
    else:
        _print_summary(manifest, args.dry_run)
        if not args.dry_run:
            out = Path(args.out_dir) / f"{manifest['sample_id']}.tar.gz"
            print(f"  -> {out}  ({_human(out.stat().st_size)})\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
