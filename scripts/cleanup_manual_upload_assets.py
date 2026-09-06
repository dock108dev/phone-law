"""Remove every generated Slice 4 input and temporary object, retaining evidence only."""

from __future__ import annotations

import os
import shutil
from pathlib import Path

ROOT = Path(os.environ.get("SLICE4_RUNTIME_ROOT", "/tmp/colacci-law-slice4-local"))  # nosec B108


def main() -> None:
    if ROOT.parent != Path("/tmp") or not ROOT.name.startswith("colacci-law-") or ROOT.is_symlink():  # nosec B108
        raise SystemExit("unsafe manual-upload cleanup root")
    for name in ("generated", "objects"):
        try:
            shutil.rmtree(ROOT / name)
        except FileNotFoundError:
            # Only an already absent tree is a successful idempotent cleanup.
            if (ROOT / name).exists():
                raise
        except OSError:
            raise SystemExit("manual-upload cleanup failed; temporary data may remain") from None
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
