"""Copy the parts of a FIRE checkout this server reads into fire_mcp/_fire/, so a
built wheel works without a separate FIRE clone.

Run before `python -m build` (the release and CI workflows do):

    python scripts/vendor_fire.py /path/to/fire --version v26.10

The checkout should be at the release tag the Dockerfile pins (ARG
FIRE_VERSION); --version is recorded in _fire/FIRE_VERSION. fire_mcp/_fire/ is
gitignored: it is a build artefact, never committed.
"""

from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

DEST = Path(__file__).resolve().parent.parent / "fire_mcp" / "_fire"

# (directory relative to the FIRE root, file pattern). Mirrors what
# fire_mcp/repo.py reads; nothing else in FIRE is needed at runtime.
_SOURCES = [
    ("schemas", "*.json"),
    ("extensions/schemas", "*.json"),
    ("documentation/properties", "*.md"),
    ("extensions/documentation/properties", "*.md"),
    ("examples", "*.json"),
]


def vendor(fire_root: Path, fire_version: str, dest: Path = DEST) -> int:
    if not (fire_root / "schemas").is_dir():
        raise SystemExit(f"{fire_root} does not look like a FIRE checkout.")
    if dest.exists():
        shutil.rmtree(dest)
    copied = 0
    for directory, pattern in _SOURCES:
        files = sorted((fire_root / directory).glob(pattern))
        if not files:
            raise SystemExit(f"No {pattern} files in {fire_root / directory}.")
        target = dest / directory
        target.mkdir(parents=True)
        for path in files:
            shutil.copy2(path, target / path.name)
            copied += 1
    # FIRE is Apache-2.0 too; its licence travels with the copied files.
    shutil.copy2(fire_root / "LICENSE", dest / "LICENSE")
    (dest / "FIRE_VERSION").write_text(f"{fire_version}\n", encoding="utf-8")
    return copied


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("fire_root", type=Path, help="Path to a FIRE checkout.")
    parser.add_argument(
        "--version", required=True, help="The FIRE release tag being vendored."
    )
    args = parser.parse_args(argv)
    copied = vendor(args.fire_root.resolve(), args.version)
    print(f"Vendored {copied} files from FIRE {args.version} into {DEST}.")


if __name__ == "__main__":
    sys.exit(main())
