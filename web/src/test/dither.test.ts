import { describe, expect, it } from "vitest"

import { BAYER, ditherImage, ditherIndex } from "@/components/argos/dither"

describe("dither", () => {
  it("has 64 distinct Bayer thresholds inside (0, 1)", () => {
    expect(BAYER).toHaveLength(64)
    expect(new Set(BAYER).size).toBe(64)
    for (const b of BAYER) {
      expect(b).toBeGreaterThan(0)
      expect(b).toBeLessThan(1)
    }
  })

  it("keeps the dither index inside a seven-tone ramp for tones below 0 and above 1", () => {
    for (const b of BAYER) {
      for (const tone of [-3, -0.01, 0, 0.5, 1, 1.01, 4, Number.NaN]) {
        const i = ditherIndex(tone, 7, b)
        expect(Number.isInteger(i)).toBe(true)
        expect(i).toBeGreaterThanOrEqual(0)
        expect(i).toBeLessThanOrEqual(6)
      }
      expect(ditherIndex(-1, 7, b)).toBe(0)
      expect(ditherIndex(2, 7, b)).toBe(6)
    }
  })

  it("prints a 2 px cell without changing the picture's size", () => {
    const ramp = ["#000000", "#ffffff"]
    const black = ditherImage(new Uint8ClampedArray([0, 0, 0, 255, 0, 0, 0, 255, 0, 0, 0, 255, 0, 0, 0, 255]), 2, 2, ramp)
    const white = ditherImage(new Uint8ClampedArray(16).map((_, i) => (i % 4 === 3 ? 255 : 255)), 2, 2, ramp)
    expect(black).toHaveLength(16)
    expect(white).toHaveLength(16)
    expect([black[0], black[1], black[2]]).toEqual([0, 0, 0])
    expect([white[0], white[1], white[2]]).toEqual([255, 255, 255])
  })
})
