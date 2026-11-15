"""Download the speech model the call agent listens with into call/models/ (not tracked).

    python tools/fetch_models.py

Vosk small US English 0.15, about 41 MB zipped, from alphacephei.com, the same model the
brain uses. Run it once per machine, while there is a network. Without it the call still
speaks and shows; it hears an acknowledgement only through Gemini.
"""

from __future__ import annotations

import sys
import urllib.request
import zipfile
from pathlib import Path

MODELS = Path(__file__).resolve().parent.parent / "models"
VOSK_URL = "https://alphacephei.com/vosk/models/vosk-model-small-en-us-0.15.zip"
VOSK_DIR = "vosk-model-small-en-us-0.15"


def download(url: str, target: Path) -> None:
    print(f"downloading {url}")
    partial = target.with_suffix(target.suffix + ".part")
    with urllib.request.urlopen(url, timeout=60) as response, partial.open("wb") as out:
        while chunk := response.read(1 << 16):
            out.write(chunk)
    partial.replace(target)
    print(f"  saved {target.name} ({target.stat().st_size // 1024} KB)")


def safe_extract(archive: Path, into: Path) -> None:
    root = into.resolve()
    with zipfile.ZipFile(archive) as zipped:
        for member in zipped.infolist():
            destination = (into / member.filename).resolve()
            if not destination.is_relative_to(root):
                raise RuntimeError(f"refusing an unsafe path in the archive: {member.filename}")
        zipped.extractall(into)


def main() -> int:
    MODELS.mkdir(parents=True, exist_ok=True)
    target = MODELS / VOSK_DIR
    if target.exists():
        print(f"{VOSK_DIR} already there")
        return 0
    archive = MODELS / f"{VOSK_DIR}.zip"
    download(VOSK_URL, archive)
    safe_extract(archive, MODELS)
    archive.unlink()
    print(f"ready: {target}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
