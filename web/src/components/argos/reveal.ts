/**
 * Unspeeded length is the glass default present (2.4 s, not passed: the sheen starts at a
 * fixed 0.9 s and runs backwards if present drops under about 1 s) plus the 1.1 s tail.
 * Speed brings that down to a second and a half.
 */
const TIMELINE_S = 2.4 + 1.1
export const REVEAL_SECONDS = 1.5
export const REVEAL_SPEED = TIMELINE_S / REVEAL_SECONDS

/** The still mark shown instead of the glass under reduced motion or without WebGL2. */
export const STILL_MS = 700

/**
 * Hand over even if the glass never reports its end. The timer starts when the reveal
 * mounts, and the glass itself starts only after its code has loaded, so this leaves that gap.
 */
export const SAFETY_MS = 4000

/*
 * Sizing for crisp line art. The engine fits the tile to min(width, height) / 1.75 and draws
 * the mark at logoScale × view. view starts at startZoom and settles near 1; finalScale is
 * applied only as the glass leaves. The light look's own finalScale is 0.69, so a startZoom
 * of 1 would still open about one and a half times larger than the end. Passing 1 keeps the
 * end at the size the mark already has once the glass is holding it.
 *
 * startSize, focus and bulge are how small, frosted and lens-like the droplet begins.
 * glide stays under the default present. A short glide lets the small leftover zoom settle
 * before the sheen, instead of carrying a magnified mark for the whole reveal.
 *
 * Two colours only: no colour split or coloured glow in the rim (they print violet and cyan),
 * and no lift shadow under the glass.
 */
export const TILE_SIZE = 560
export const LOGO_SCALE = 0.8
export const FINAL_SCALE = 1
export const TUNING = {
  startZoom: 1.08,
  startSize: 0.14,
  focus: 0.4,
  bulge: 0.3,
  glide: 0.6,
  ripple: 0.5,
  dispersion: 0,
  colorBleed: 0,
  shadow: 0,
}

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
