import { describe, expect, it } from "vitest"

import { BAYER, ditherIndex } from "@/components/argos/dither"

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
})
