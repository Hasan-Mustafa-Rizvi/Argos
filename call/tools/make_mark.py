"""Make `call/assets/argos-mark.png` from `design/logo/argos-mark.svg`. Run once:

    python tools/make_mark.py

The mark is one path of absolute M, C, L and Z commands with the even-odd fill rule. Each
subpath is flattened to a polygon and drawn onto a mask, and the masks are combined with XOR,
which is exactly even-odd. Drawn four times larger and scaled down, for smooth edges. Cobalt
(`#2238c4`, the calm colour in design/IDENTITY.md) on a transparent background.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

from PIL import Image, ImageChops, ImageDraw

REPO = Path(__file__).resolve().parents[2]
SOURCE = REPO / "design" / "logo" / "argos-mark.svg"
TARGET = Path(__file__).resolve().parents[1] / "assets" / "argos-mark.png"
COBALT = (34, 56, 196)
SIZE = 512
SCALE = 4
STEPS = 12  # points per curve segment


def subpaths(d: str) -> list[list[tuple[float, float]]]:
    tokens = re.findall(r"[MCLZ]|-?\d*\.?\d+(?:e-?\d+)?", d)
    shapes: list[list[tuple[float, float]]] = []
    current: list[tuple[float, float]] = []
    command = ""
    i = 0
    while i < len(tokens):
        token = tokens[i]
        if token in "MCLZ":
            command = token
            i += 1
            if command == "Z":
                if current:
                    shapes.append(current)
                current = []
            continue
        if command == "M":
            if current:
                shapes.append(current)
            current = [(float(tokens[i]), float(tokens[i + 1]))]
            i += 2
            command = "L"
        elif command == "L":
            current.append((float(tokens[i]), float(tokens[i + 1])))
            i += 2
        elif command == "C":
            x0, y0 = current[-1]
            x1, y1, x2, y2, x3, y3 = (float(t) for t in tokens[i:i + 6])
            for step in range(1, STEPS + 1):
                t = step / STEPS
                u = 1 - t
                current.append((
                    u**3 * x0 + 3 * u * u * t * x1 + 3 * u * t * t * x2 + t**3 * x3,
                    u**3 * y0 + 3 * u * u * t * y1 + 3 * u * t * t * y2 + t**3 * y3,
                ))
            i += 6
        else:
            raise ValueError(f"unexpected token {token!r}")
    if current:
        shapes.append(current)
    return shapes


def main() -> int:
    svg = SOURCE.read_text(encoding="utf-8")
    view = [float(v) for v in re.search(r'viewBox="([^"]+)"', svg).group(1).split()]
    path = re.search(r"<path[^>]*>", svg).group(0)
    d = re.search(r'\bd="([^"]+)"', path).group(1)
    move = re.search(r"translate\(([-\d.]+)[ ,]+([-\d.]+)\)", path)
    zoom = re.search(r"scale\(([-\d.]+)\)", path)
    dx, dy = (float(move.group(1)), float(move.group(2))) if move else (0.0, 0.0)
    k = float(zoom.group(1)) if zoom else 1.0
    big = SIZE * SCALE
    factor = big / max(view[2], view[3])
    mask = Image.new("1", (big, big), 0)
    for shape in subpaths(d):
        points = [((x * k + dx - view[0]) * factor, (y * k + dy - view[1]) * factor)
                  for x, y in shape]
        layer = Image.new("1", (big, big), 0)
        ImageDraw.Draw(layer).polygon(points, fill=1)
        mask = ImageChops.logical_xor(mask, layer)
    alpha = mask.convert("L").resize((SIZE, SIZE), Image.LANCZOS)
    image = Image.new("RGBA", (SIZE, SIZE), (*COBALT, 0))
    image.putalpha(alpha)
    TARGET.parent.mkdir(parents=True, exist_ok=True)
    image.save(TARGET, optimize=True)
    print(f"wrote {TARGET} ({TARGET.stat().st_size // 1024} KB)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
