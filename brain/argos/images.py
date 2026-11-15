"""JPEG encoding, in memory only. Nothing here touches the disk."""

from __future__ import annotations

from typing import Any


def scaled(image: Any, max_side: int) -> Any:
    import cv2

    height, width = image.shape[:2]
    longest = max(height, width)
    if longest <= max_side:
        return image
    scale = max_side / longest
    size = (max(1, int(round(width * scale))), max(1, int(round(height * scale))))
    return cv2.resize(image, size, interpolation=cv2.INTER_AREA)


def jpeg(image: Any, max_side: int = 1280, quality: int = 85) -> bytes:
    import cv2

    ok, data = cv2.imencode(".jpg", scaled(image, max_side),
                            [int(cv2.IMWRITE_JPEG_QUALITY), int(quality)])
    if not ok:
        raise ValueError("JPEG encoding failed")
    return data.tobytes()


def image_of(frame: Any) -> Any:
    """The pixel array inside a camera Frame (or the array itself)."""
    return getattr(frame, "image", frame)
