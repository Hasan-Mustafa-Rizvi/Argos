"""What the agent shows: one picture at a fixed size, changed as the call goes on.

Three kinds, in this order of preference:

1. `live`: the dog's camera, from live view frames as they arrive (contract section 6).
2. `snapshot`: the one stored picture of the incident.
3. `card`: the Argos mark on paper, with the time.

Every picture is made in memory and replaced by the next. Nothing is written to disk.
"""

from __future__ import annotations

import io
import logging
import threading
from collections.abc import Callable
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

log = logging.getLogger("argos_call.picture")

ASSETS = Path(__file__).resolve().parent.parent / "assets"
MARK = ASSETS / "argos-mark.png"

PAPER = (247, 244, 236)
COBALT = (34, 56, 196)
NIGHT = (8, 14, 34)
CAPTION_INK = (247, 244, 236)


def _font(size: int) -> ImageFont.ImageFont | ImageFont.FreeTypeFont:
    try:
        return ImageFont.load_default(size=size)
    except TypeError:  # an old Pillow without a scalable default font
        return ImageFont.load_default()


class Picture:
    def __init__(self, width: int = 1280, height: int = 720) -> None:
        self.width = width
        self.height = height
        self.kind = "card"
        self._lock = threading.Lock()
        self._mark: Image.Image | None = None
        try:
            self._mark = Image.open(MARK).convert("RGBA")
        except OSError:
            log.warning("the Argos mark is missing at %s; the card shows text only", MARK)
        self._rgba = b""
        self.show_card("Argos", "")

    def rgba(self) -> bytes:
        with self._lock:
            return self._rgba

    def _set(self, image: Image.Image, kind: str) -> None:
        data = image.convert("RGBA").tobytes()
        with self._lock:
            self._rgba = data
            self.kind = kind

    # ------------------------------------------------------------------ the three kinds

    def show_card(self, title: str, subtitle: str) -> None:
        image = Image.new("RGB", (self.width, self.height), PAPER)
        draw = ImageDraw.Draw(image)
        side = int(self.height * 0.5)
        top = int(self.height * 0.12)
        if self._mark is not None:
            mark = self._mark.resize((side, side), Image.LANCZOS)
            image.paste(mark, ((self.width - side) // 2, top), mark)
        y = top + side + int(self.height * 0.05)
        for text, size in ((title, int(self.height * 0.075)), (subtitle, int(self.height * 0.05))):
            if not text:
                continue
            font = _font(size)
            box = draw.textbbox((0, 0), text, font=font)
            draw.text(((self.width - (box[2] - box[0])) // 2, y), text, fill=COBALT, font=font)
            y += (box[3] - box[1]) + int(self.height * 0.03)
        self._set(image, "card")

    def show_jpeg(self, jpeg: bytes, caption: str, kind: str) -> bool:
        """A JPEG (a live frame or the snapshot), fitted onto the night panel with a caption.
        False if it cannot be read."""
        try:
            photo = Image.open(io.BytesIO(jpeg))
            photo.load()
        except Exception:
            return False
        image = Image.new("RGB", (self.width, self.height), NIGHT)
        strip = int(self.height * 0.11) if caption else 0
        room_w, room_h = self.width, self.height - strip
        scale = min(room_w / photo.width, room_h / photo.height)
        size = (max(1, int(photo.width * scale)), max(1, int(photo.height * scale)))
        photo = photo.convert("RGB").resize(size, Image.BILINEAR)
        image.paste(photo, ((room_w - size[0]) // 2, (room_h - size[1]) // 2))
        if caption:
            draw = ImageDraw.Draw(image)
            font = _font(int(strip * 0.45))
            box = draw.textbbox((0, 0), caption, font=font)
            draw.text(((self.width - (box[2] - box[0])) // 2,
                       self.height - strip + (strip - (box[3] - box[1])) // 2 - box[1]),
                      caption, fill=CAPTION_INK, font=font)
        self._set(image, kind)
        return True


class Screen:
    """Chooses what is on the agent's video: live frames while they arrive, else the stored
    snapshot, else the card. The latest live JPEG is held in memory only, for one reason: so
    Gemini can be shown what the camera sees now when the person asks."""

    def __init__(self, picture: Picture, time_text: str, now: Callable[[], float]) -> None:
        self.picture = picture
        self.time_text = time_text
        self.now = now
        self.snapshot: bytes | None = None
        self.latest_live: bytes | None = None
        self._live_at: float | None = None
        self.show_fallback()

    def set_snapshot(self, jpeg: bytes | None) -> None:
        if jpeg and self.picture.show_jpeg(jpeg, f"The picture I took at {self.time_text}",
                                           "snapshot"):
            self.snapshot = jpeg
        elif jpeg:
            log.warning("the stored snapshot could not be read; showing the card")

    def live(self, jpeg: bytes) -> None:
        if self.picture.show_jpeg(jpeg, "Live: what Argos sees now", "live"):
            self.latest_live = jpeg
            self._live_at = self.now()

    def tick(self) -> None:
        """Back to the snapshot or the card once live frames have stopped for 5 seconds."""
        if self._live_at is not None and self.now() - self._live_at >= 5.0:
            self._live_at = None
            self.latest_live = None
            self.show_fallback()

    def show_fallback(self) -> None:
        if self.snapshot and self.picture.show_jpeg(
                self.snapshot, f"The picture I took at {self.time_text}", "snapshot"):
            return
        self.picture.show_card("Argos", f"Alert at {self.time_text}")

    @property
    def kind(self) -> str:
        return self.picture.kind

    def describe(self) -> str:
        return {"live": "the live view of Argos's camera",
                "snapshot": f"the picture Argos took at {self.time_text}"}.get(
                    self.kind, "the Argos card, with no picture")
