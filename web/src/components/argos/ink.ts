/*
 * The inks from design/IDENTITY.md section 1, for code that draws on a canvas and cannot read
 * CSS variables. tokens.css holds the same values for everything else; a test keeps them equal.
 */

export type InkState = "calm" | "checking" | "alert" | "offline"

export const INK_STATES: readonly InkState[] = ["calm", "checking", "alert", "offline"]

export const PAPER = "#f7f4ec"

export const STATE_INK: Readonly<Record<InkState, string>> = {
  calm: "#2238c4",
  checking: "#8a5a0b",
  alert: "#7a1d2b",
  offline: "#46547e",
}

export const STATE_WORDS: Readonly<Record<InkState, string>> = {
  calm: "Calm",
  checking: "Checking",
  alert: "Alert",
  offline: "Offline",
}

/** The cobalt-on-paper ramp exactly as IDENTITY.md prints it, light to dark. */
export const COBALT_RAMP: readonly string[] = ["#f7f4ec", "#dadfea", "#b4c3e6", "#8ba3e0", "#607fd7", "#3c5cce", "#2238c4"]

/** The night ramp exactly as IDENTITY.md prints it, dark to light. */
export const NIGHT_RAMP: readonly string[] = ["#080e22", "#1a2134", "#373d4e", "#606571", "#91939a", "#c5c5c4", "#f7f4ec"]

/** IDENTITY.md: mix ink into paper at these shares for any other ink. */
export const PAPER_RAMP_STOPS: readonly number[] = [0, 0.12, 0.28, 0.46, 0.66, 0.84, 1]

/** The shares that reproduce the printed night ramp: paper into night, in OKLab. */
export const NIGHT_RAMP_STOPS: readonly number[] = [0, 0.1, 0.24, 0.42, 0.62, 0.82, 1]

type Rgb = [number, number, number]

function parseHex(hex: string): Rgb {
  let h = hex.replace("#", "")
  if (h.length === 3) h = h.replace(/./g, "$&$&")
  const v = parseInt(h.slice(0, 6), 16) || 0
  return [((v >> 16) & 255) / 255, ((v >> 8) & 255) / 255, (v & 255) / 255]
}

function toHex(c: Rgb): string {
  return "#" + c.map((v) => Math.round(Math.min(1, Math.max(0, v)) * 255).toString(16).padStart(2, "0")).join("")
}

const toLinear = (v: number) => (v <= 0.04045 ? v / 12.92 : Math.pow((v + 0.055) / 1.055, 2.4))
const fromLinear = (v: number) => (v <= 0.0031308 ? 12.92 * v : 1.055 * Math.pow(v, 1 / 2.4) - 0.055)

function toOklab([r0, g0, b0]: Rgb): Rgb {
  const r = toLinear(r0)
  const g = toLinear(g0)
  const b = toLinear(b0)
  const l = Math.cbrt(0.4122214708 * r + 0.5363325363 * g + 0.0514459929 * b)
  const m = Math.cbrt(0.2119034982 * r + 0.6806995451 * g + 0.1073969566 * b)
  const s = Math.cbrt(0.0883024619 * r + 0.2817188376 * g + 0.6299787005 * b)
  return [
    0.2104542553 * l + 0.793617785 * m - 0.0040720468 * s,
    1.9779984951 * l - 2.428592205 * m + 0.4505937099 * s,
    0.0259040371 * l + 0.7827717662 * m - 0.808675766 * s,
  ]
}

function fromOklab([L, a, b]: Rgb): Rgb {
  const l = (L + 0.3963377774 * a + 0.2158037573 * b) ** 3
  const m = (L - 0.1055613458 * a - 0.0638541728 * b) ** 3
  const s = (L - 0.0894841775 * a - 1.291485548 * b) ** 3
  return [
    fromLinear(4.0767416621 * l - 3.3077115913 * m + 0.2309699292 * s),
    fromLinear(-1.2684380046 * l + 2.6097574011 * m - 0.3413193965 * s),
    fromLinear(-0.0041960863 * l - 0.7034186147 * m + 1.707614701 * s),
  ]
}

/** CSS `color-mix(in oklab, a share, b)`. */
export function mixOklab(a: string, b: string, share: number): string {
  const A = toOklab(parseHex(a))
  const B = toOklab(parseHex(b))
  return toHex(fromOklab([0, 1, 2].map((i) => A[i] * share + B[i] * (1 - share)) as Rgb))
}

/** Seven tones from paper to the ink, mixed as IDENTITY.md describes. */
export function paperRamp(ink: string): string[] {
  return PAPER_RAMP_STOPS.map((p) => mixOklab(ink, PAPER, p))
}

/** Seven tones from the ink's night to paper, for drawing on the night panel. */
export function nightRamp(ink: string): string[] {
  const night = mixOklab(ink, "#05060b", 0.15)
  return NIGHT_RAMP_STOPS.map((p) => mixOklab(PAPER, night, p))
}

/** Linear blend between two equal-length ramps, for the 600 ms reprint on a canvas. */
export function blendRamps(from: readonly string[], to: readonly string[], t: number): string[] {
  if (t >= 1 || from.length !== to.length) return [...to]
  return to.map((hex, i) => {
    const a = parseHex(from[i])
    const b = parseHex(hex)
    return toHex([0, 1, 2].map((k) => a[k] + (b[k] - a[k]) * t) as Rgb)
  })
}

/** Packs a ramp into 0xAABBGGRR words for writing straight into ImageData. */
export function packRamp(ramp: readonly string[]): Uint32Array {
  const out = new Uint32Array(ramp.length)
  ramp.forEach((hex, i) => {
    const [r, g, b] = parseHex(hex)
    out[i] = (255 << 24) | (Math.round(b * 255) << 16) | (Math.round(g * 255) << 8) | Math.round(r * 255)
  })
  return out
}
