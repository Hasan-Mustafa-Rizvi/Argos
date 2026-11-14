/*
 * Ordered dither and value noise. BAYER, ditherIndex, hash, noise, fbm and smooth are adapted
 * from RDF_BAYER, rdfDither, rdfHash, rdfNoise, rdfFbm and rdfSmooth in the Ridgeline Dither
 * Footer (21st.dev community component); see CREDITS.md. The scene below is our own.
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

export function hash(x: number, y: number, seed: number): number {
  let h = Math.imul(x | 0, 374761393) + Math.imul(y | 0, 668265263) + Math.imul(seed | 0, 1442695041)
  h = Math.imul(h ^ (h >>> 13), 1274126177)
  h ^= h >>> 16
  return (h >>> 0) / 4294967296
}

/** Smooth value noise in [0, 1). */
export function noise(x: number, y: number, seed: number): number {
  const xi = Math.floor(x)
  const yi = Math.floor(y)
  const xf = x - xi
  const yf = y - yi
  const u = xf * xf * (3 - 2 * xf)
  const v = yf * yf * (3 - 2 * yf)
  const a = hash(xi, yi, seed)
  const b = hash(xi + 1, yi, seed)
  const c = hash(xi, yi + 1, seed)
  const d = hash(xi + 1, yi + 1, seed)
  return a + (b - a) * u + (c - a) * v + (a - b - c + d) * u * v
}

/** Fractal value noise, normalised back into [0, 1). */
export function fbm(x: number, y: number, seed: number, octaves: number): number {
  let sum = 0
  let amp = 0.5
  let norm = 0
  for (let o = 0; o < octaves; o++) {
    sum += noise(x, y, seed + o * 31) * amp
    norm += amp
    x *= 2.03
    y *= 2.03
    amp *= 0.5
  }
  return norm > 0 ? sum / norm : 0
}

/** Hermite step from e0 to e1, clamped. */
export function smooth(e0: number, e1: number, x: number): number {
  const t = e1 === e0 ? (x < e0 ? 0 : 1) : Math.min(1, Math.max(0, (x - e0) / (e1 - e0)))
  return t * t * (3 - 2 * t)
}

const mix = (a: number, b: number, t: number) => a + (b - a) * t

/*
 * The scene: a ridgeline on the horizon over the sea, the island seen from far off. On a tall
 * panel it is one island; on a wide strip the same rule makes a chain of them.
 */

export interface SceneField {
  cols: number
  rows: number
  /** Tone of every cell before the sea and the mist move, row by row. */
  base: Float32Array
  /** Row of the horizon. */
  horizon: number
  /** Island cover above each column of the sea, 0 to 1, for the reflection. */
  cover: Float32Array
}

function ridged(u: number, freq: number, seed: number): number {
  const r1 = 1 - Math.abs(noise(u * freq, 0.5, seed) * 2 - 1)
  const r2 = 1 - Math.abs(noise(u * freq * 2.3, 3.5, seed + 1) * 2 - 1)
  const f = fbm(u * freq * 4.1, 9.5, seed + 2, 3)
  return r1 * r1 * 0.62 + r2 * 0.24 + f * 0.14
}

export function sceneField(cols: number, rows: number, seed: number): SceneField {
  const aspect = cols / Math.max(1, rows)
  const wide = Math.min(1, Math.max(0, (aspect - 1) / 6))
  const horizon = Math.round(rows * mix(0.64, 0.8, wide))
  const lift = rows * mix(0.2, 0.5, wide)
  // One island in a tall panel; a long strip becomes a ridgeline of at most three.
  const islands = Math.min(3, Math.max(1, Math.round(aspect / 4)))
  const base = new Float32Array(cols * rows)
  const cover = new Float32Array(cols)
  const SLOPE_REACH = 4

  // Two layers: a taller far ridge, lighter in the haze, and the nearer island in front of it.
  const layers = [
    { height: 1, tone: 0.36, freq: 5.5, shift: 0.07, s: seed * 13 + 101 },
    { height: 0.62, tone: 0.66, freq: 3.4, shift: -0.05, s: seed * 13 + 202 },
  ]
  const crests = layers.map((L, li) => {
    const out = new Float32Array(cols)
    for (let x = 0; x < cols; x++) {
      const u = x / Math.max(1, cols - 1)
      const pos = u * islands
      const k = Math.min(islands - 1, Math.floor(pos))
      const t = pos - k + L.shift
      const j0 = hash(k, li, seed)
      const j1 = hash(k, li + 7, seed)
      const rise = smooth(0.06 + 0.12 * j0, 0.36 + 0.1 * j0, t)
      const fall = 1 - smooth(0.62 + 0.1 * j1, 0.94 + 0.04 * j1, t)
      const h = L.height * lift * rise * fall * (0.5 + 0.5 * ridged(u * islands, L.freq / islands + 1.2, L.s))
      out[x] = horizon - h
      if (li === 1) cover[x] = Math.min(1, h / Math.max(1, lift * 0.35))
    }
    return out
  })

  for (let y = 0; y < rows; y++) {
    const v = y / Math.max(1, rows - 1)
    for (let x = 0; x < cols; x++) {
      const u = x / Math.max(1, cols - 1)
      let tone: number
      if (y < horizon) {
        // Sky: paper, thickening a little toward the horizon, with a faint drift of cloud.
        const toward = smooth(0, horizon, y)
        tone = 0.02 + 0.14 * toward * toward + 0.08 * (fbm(u * 3 * aspect, v * 7, seed + 5, 3) - 0.5) * toward
        for (let li = 0; li < layers.length; li++) {
          const c = crests[li][x]
          if (y < c) continue
          // Light from the left: the flank facing it is lighter near the crest and fades below.
          const left = crests[li][Math.max(0, x - SLOPE_REACH)]
          const right = crests[li][Math.min(cols - 1, x + SLOPE_REACH)]
          const slope = Math.max(-1, Math.min(1, ((right - left) / (2 * SLOPE_REACH)) * 1.6))
          const depth = (y - c) / Math.max(1, horizon - c)
          const lit = 1 - smooth(0, 0.55, depth)
          const rock = fbm(u * 9 * aspect, v * 9, seed + 31 + li, 3) - 0.5
          tone =
            layers[li].tone +
            0.12 * slope * lit -
            0.08 * depth +
            0.1 * rock +
            0.04 * (hash(x, y, seed + li) - 0.5)
          if (y - c < 1.5) tone += 0.2
        }
      } else {
        // Sea: darker toward the viewer, with the island's reflection just under the horizon.
        const near = (y - horizon) / Math.max(1, rows - horizon)
        tone = 0.2 + 0.42 * Math.pow(near, 1.2) + 0.22 * cover[x] * (1 - smooth(0, 0.35, near))
        if (y === horizon) tone += 0.25
      }
      base[y * cols + x] = tone
    }
  }
  return { cols, rows, base, horizon, cover }
}

/**
 * The moving part: ripples on the sea and mist along the horizon, added to the base tone.
 * `t` is in seconds.
 */
export function sceneMotion(field: SceneField, x: number, y: number, t: number, seed: number): number {
  const { cols, rows, horizon } = field
  const u = x / Math.max(1, cols - 1)
  if (y > horizon) {
    const near = (y - horizon) / Math.max(1, rows - horizon)
    const streak = noise(u * cols * 0.045 + t * 0.35, (y - horizon) * 0.55, seed + 11)
    return 0.16 * (streak - 0.5) * (0.4 + near)
  }
  const band = 1 - smooth(0, rows * 0.16, Math.abs(y - (horizon - rows * 0.05)))
  if (band <= 0) return 0
  const mist = fbm(u * 2.4 * (cols / Math.max(1, rows)) + t * 0.03, y * 0.05, seed + 17, 2)
  return -0.26 * band * smooth(0.45, 0.8, mist)
}
