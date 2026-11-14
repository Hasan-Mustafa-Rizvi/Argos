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

/** Which of `n` ramp tones a cell prints at `tone` (0 paper, 1 ink) under `threshold`. */
export function ditherIndex(tone: number, n: number, threshold: number): number {
  const t = tone > 0 ? (tone < 1 ? tone : 1) : 0
  const v = Math.floor(t * (n - 1) + threshold)
  return v > n - 1 ? n - 1 : v < 0 ? 0 : v
}
