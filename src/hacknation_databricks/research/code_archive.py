"""Keep framework provenance separate from a source-bound experiment implementation."""

from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile


def archive_framework(output):
    target = output / "framework/source.zip"
    target.parent.mkdir(parents=True, exist_ok=True)
    with ZipFile(target, "w", compression=ZIP_DEFLATED) as archive:
        for module in sorted(Path(__file__).parent.glob("*.py")):
            archive.write(module, arcname=module.name)
