import { describe, expect, it } from "vitest"

import * as glass from "@/components/ui/liquid-glass-logo-reveal"

describe("the copied glass reveal", () => {
  it("exports GlassIconReveal and not the 21st.dev wrapper", () => {
    expect(typeof glass.GlassIconReveal).toBe("function")
    expect(Object.keys(glass)).not.toContain("GlassReveal21st")
    expect(Object.keys(glass)).not.toContain("default")
  })
})
