/*
 * Ordered dither. BAYER and ditherIndex are adapted from RDF_BAYER and rdfDither in the
 * Ridgeline Dither Footer (21st.dev community component); see CREDITS.md. The landscape
 * that used to sit on top of this is gone: the camera view is the only dither still planned.
 */

/** The 8 × 8 Bayer matrix as 64 thresholds in (0, 1), row by row. */
export const BAYER: readonly number[] = [
  0, 32, 8, 40, 2, 34, 10, 42, 48, 16, 56, 24, 50, 18, 58, 26,
  12, 44, 4, 36, 14, 46, 6, 38, 60, 28, 52, 20, 62, 30, 54, 22,
  3, 35, 11, 43, 1, 33, 9, 41, 51, 19, 59, 27, 49, 17, 57, 25,
  15, 47, 7, 39, 13, 45, 5, 37, 63, 31, 55, 23, 61, 29, 53, 21,
].map((v) => (v + 0.5) / 64)

/** Luma of one pixel, 0 black to 1 white. The ramp then runs dark to light. */
function luma(data: Uint8ClampedArray, index: number): number {
  return (0.2126 * data[index] + 0.7152 * data[index + 1] + 0.0722 * data[index + 2]) / 255
}

function hexRgb(hex: string): [number, number, number] {
  const v = parseInt(hex.slice(1), 16)
  return [(v >> 16) & 255, (v >> 8) & 255, v & 255]
}

/**
 * Print `src` as 2 px Bayer cells. The result is a new buffer the same size, so the picture
 * keeps its shape. A dark-to-light ramp (the night panel) is used as it stands: black takes
 * the first colour. A light-to-dark ramp (paper to ink) passes `invert`, so black takes the last.
 */
export function ditherImage(
  src: Uint8ClampedArray,
  width: number,
  height: number,
  ramp: readonly string[],
  invert = false,
): Uint8ClampedArray {
  const out = new Uint8ClampedArray(src.length)
  const colours = ramp.map(hexRgb)
  const n = colours.length || 1
  for (let y = 0; y < height; y += 2) {
    for (let x = 0; x < width; x += 2) {
      let sum = 0
      let count = 0
      for (let dy = 0; dy < 2 && y + dy < height; dy++) {
        for (let dx = 0; dx < 2 && x + dx < width; dx++) {
          sum += luma(src, ((y + dy) * width + (x + dx)) * 4)
          count++
        }
      }
      const seen = count ? sum / count : 0
      const tone = invert ? 1 - seen : seen
      const index = ditherIndex(tone, n, BAYER[(Math.floor(y / 2) % 8) * 8 + (Math.floor(x / 2) % 8)])
      const [r, g, b] = colours[index] ?? [0, 0, 0]
      for (let dy = 0; dy < 2 && y + dy < height; dy++) {
        for (let dx = 0; dx < 2 && x + dx < width; dx++) {
          const i = ((y + dy) * width + (x + dx)) * 4
          out[i] = r
          out[i + 1] = g
          out[i + 2] = b
          out[i + 3] = 255
        }
      }
    }
  }
  return out
}

/** Which of `n` ramp tones a cell prints at `tone` (0 paper, 1 ink) under `threshold`. */
export function ditherIndex(tone: number, n: number, threshold: number): number {
  const t = tone > 0 ? (tone < 1 ? tone : 1) : 0
  const v = Math.floor(t * (n - 1) + threshold)
  return v > n - 1 ? n - 1 : v < 0 ? 0 : v
}
