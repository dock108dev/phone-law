"""Remove every generated Slice 4 input and temporary object, retaining evidence only."""

from __future__ import annotations

import shutil
from pathlib import Path

ROOT = Path("/tmp/colacci-law-slice4-local")  # nosec B108


def main() -> None:
    if Path("/tmp/colacci-law-slice4-local") != ROOT:  # nosec B108
        raise SystemExit("unsafe manual-upload cleanup root")
    for name in ("generated", "objects"):
        shutil.rmtree(ROOT / name, ignore_errors=True)
    (ROOT / "synthetic-manifest.json").unlink(missing_ok=True)
    remaining_media = sum(
        1
        for path in ROOT.rglob("*")
        if path.is_file() and path.suffix.lower() in {".wav", ".mp3", ".m4a", ".mp4", ".webm"}
    )
    if remaining_media:
        raise SystemExit("generated manual-upload media remains")
    print("manual-upload-cleanup generated_media=0 temporary_objects=0")


if __name__ == "__main__":
    main()
