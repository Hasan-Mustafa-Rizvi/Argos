/** The reveal's timeline ends at 3.5 s at speed 1; this speed makes it about 3 s. */
export const REVEAL_SECONDS = 3
export const REVEAL_SPEED = 3.5 / REVEAL_SECONDS

/** The still mark shown instead of the glass under reduced motion or without WebGL2. */
export const STILL_MS = 700

/** Hand over even if the glass never reports its end: the reveal must never trap anyone. */
export const SAFETY_MS = 6000

/*
 * Sizing for crisp line art. The engine fits the tile to min(width, height) / 1.75 and draws
 * the finished mark at logoScale × 0.955 × finalScale (0.69 in the light look) of the tile,
 * from a 768 px field. TILE_SIZE sits above that fit so the tile always fills it.
 *
 * Two colours only: no colour split or coloured glow in the rim (they print violet and cyan),
 * and no lift shadow under the glass.
 */
export const TILE_SIZE = 560
export const LOGO_SCALE = 0.8
export const TUNING = { startZoom: 2.2, dispersion: 0, colorBleed: 0, shadow: 0 }

const REVEAL_KEY = "argos.reveal"

/** The reveal plays at most once per tab session. Signing out does not clear this. */
export function revealPlayed(): boolean {
  try {
    return window.sessionStorage.getItem(REVEAL_KEY) === "played"
  } catch {
    return false
  }
}

export function markRevealPlayed() {
  try {
    window.sessionStorage.setItem(REVEAL_KEY, "played")
  } catch {
    // Without storage it may play again on the next entry, which is harmless.
  }
}

export function supportsWebGL2(): boolean {
  if (typeof WebGL2RenderingContext === "undefined") return false
  try {
    const gl = document.createElement("canvas").getContext("webgl2")
    if (!gl) return false
    gl.getExtension("WEBGL_lose_context")?.loseContext()
    return true
  } catch {
    return false
  }
}

export function reducedMotion(): boolean {
  return typeof window.matchMedia === "function" && window.matchMedia("(prefers-reduced-motion: reduce)").matches
}
