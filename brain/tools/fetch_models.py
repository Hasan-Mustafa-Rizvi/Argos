"""Download the two model files the senses need into brain/models/ (not tracked by git).

    python tools/fetch_models.py

- Pose: MediaPipe Pose Landmarker lite (float16), about 5.8 MB, from Google's model store.
- Speech: Vosk small US English 0.15, about 41 MB zipped, from alphacephei.com.

Both come from their publishers' own download addresses. Run it once per machine, while there
is a network. The brain runs without them: it says so, and the camera triggers or listening
are simply off.
"""

from __future__ import annotations

import sys
import urllib.request
import zipfile
from pathlib import Path

MODELS = Path(__file__).resolve().parent.parent / "models"
POSE_URL = ("https://storage.googleapis.com/mediapipe-models/pose_landmarker/"
            "pose_landmarker_lite/float16/latest/pose_landmarker_lite.task")
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
    pose = MODELS / "pose_landmarker_lite.task"
    if pose.exists():
        print(f"{pose.name} already there")
    else:
        download(POSE_URL, pose)
    vosk_dir = MODELS / VOSK_DIR
    if vosk_dir.exists():
        print(f"{VOSK_DIR} already there")
    else:
        archive = MODELS / f"{VOSK_DIR}.zip"
        download(VOSK_URL, archive)
        safe_extract(archive, MODELS)
        archive.unlink()
        print(f"  unpacked {VOSK_DIR}")
    print("done")
    return 0


if __name__ == "__main__":
    sys.exit(main())
