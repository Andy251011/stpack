# Repository guidelines for AI coding agents

## What this project is

`stpack` takes one raw spatial transcriptomics sample folder (10x Xenium or
Visium output) and produces one standardised `.tar.gz` containing only the
files the lab needs, renamed to a common scheme, plus a `manifest.json`
recording what was kept, what was dropped, and why.

Context: a UC Irvine computational biology lab processes many spatial
samples. Every platform lays its output out differently, and each ships the
same data several times over in different encodings. Downstream code should
not have to know which platform a sample came from.

## Who works on this

An undergraduate biology major with a CS minor, learning Python as he goes.
Therefore:

- **Explain every change in plain language.** Say what the code does and
  why, not just that it is done.
- **Prefer obvious code over clever code.** No metaclasses, no decorators
  beyond `@dataclass`, no comprehensions nested more than one deep.
- **Do not introduce a dependency without saying why it is needed** and
  what it would cost to avoid. The core currently has zero dependencies
  beyond the standard library; keep it that way unless a task genuinely
  requires otherwise (image I/O and ML work will need them — add those as
  optional extras, not core dependencies).
- **Never silently rewrite a biological decision.** Which files matter and
  why is the lab's call, not the agent's.

## Architecture

```
src/stpack/
  keeplists.py   # THE decision table: which files to keep per platform
  detect.py      # identify platform from signature files
  package.py     # execute the keep-list: copy, rename, checksum, tar
  cli.py         # argparse front end
tests/
  make_fixtures.py  # synthetic 10x folder layouts (junk bytes, real names)
  test_package.py
```

`keeplists.py` is data, not logic. Changing what gets kept should mean
editing that file only. If a change to the keep-list forces a change in
`package.py`, that is a sign the abstraction needs extending (as happened
when folders had to be supported alongside files).

## Conventions

- Python >= 3.10. Type hints on all public functions.
- `pathlib.Path`, never string paths or `os.path`.
- Standard library only in the core package. Dev extras may add `pytest`.
- Read large files in chunks; a sample's image can be 2 GB and must never
  be loaded into memory whole.
- Fail loudly on a missing *required* file. A silently incomplete archive
  is worse than no archive.
- Every keep-list entry carries a `note` explaining why it is kept; the
  note ends up in the manifest. Dropped paths carry a reason in the
  `dropped` dict for the same purpose.

## Testing

```bash
python -m pytest tests/
```

Tests must run with no data download. `tests/make_fixtures.py` builds fake
sample folders whose filenames and nesting match real 10x output; contents
are junk bytes because file *selection* is what is under test.

When adding a keep-list rule, add a test that pins the decision — e.g.
"the 3D stack is preferred over the MIP" — so a later edit cannot quietly
reverse a decision the lab signed off on.

## Decisions already reviewed — do not reverse without being asked

Reviewed with the lab on 2026-09-30:

- Duplicate encodings (`.csv.gz`, `.zarr.zip`, MTX folders) are dropped.
- Filenames are standardised across platforms (`expression.h5` etc.).
- The 10x `analysis/` folder **is kept**, even though its contents are
  clusters rather than cell types.
- The Xenium image kept is the **full 3D `morphology.ome.tif`** (~2 GB),
  because the z-axis is sometimes needed. The MIP is kept alongside it.
- `transcripts.parquet` is **off by default** (no re-segmentation planned)
  but reachable via `--with-transcripts`.

## Next planned work

Segment nuclei in the full-resolution H&E with CellViT, then assign
expression from the existing cell x gene matrix onto the CellViT cells, to
get a coarse cell type per cell independent of the vendor's segmentation.

Unresolved before that can start:

1. CellViT is trained on H&E (PanNuke). The Xenium morphology image is DAPI
   fluorescence, not H&E, so CellViT cannot be pointed at it directly.
   Which image is the intended input needs settling.
2. Re-assigning expression without `transcripts.parquet` means matching
   vendor cells to CellViT cells geometrically and transferring whole
   expression vectors — which inherits the vendor's assignment errors. If
   the goal is to correct those errors, transcript-level data is required.

Do not start implementing either step until these are answered.
