import { describe, expect, it } from "vitest"

/** Built here so this file does not contain the phrases it forbids. */
const banned = ["service" + "_role", "service" + " role", "secret" + " key", "secret" + "_key", "sb_" + "secret"]

const sources = import.meta.glob(["../**/*.{ts,tsx,css,json}"], {
  query: "?raw",
  import: "default",
  eager: true,
})

describe("rule 1", () => {
  it("keeps service credentials and project addresses out of the source", () => {
    const project = new RegExp("https?://[a-z0-9-]+\\." + "supabase" + "\\.co", "i")
    const jwt = new RegExp("eyJ" + "[A-Za-z0-9_-]{20,}")
    const files = Object.entries(sources)
    expect(files.length).toBeGreaterThan(10)
    for (const [file, text] of files) {
      if (typeof text !== "string") continue
      for (const word of banned) expect(text.toLowerCase(), file).not.toContain(word)
      expect(text, file).not.toMatch(project)
      expect(text, file).not.toMatch(jwt)
    }
  })
})
