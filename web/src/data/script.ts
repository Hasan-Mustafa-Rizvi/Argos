import scenario from "./demo_scenario.jsonl?raw"

import type { ScriptLine } from "./contract"

/**
 * Reads a scripted run, one JSON object per line. Lines that are not valid are skipped, and
 * the rest are ordered by `offset_ms`, keeping file order for lines at the same moment.
 */
export function parseScript(text: string, log: (message: string) => void = () => {}): ScriptLine[] {
  const lines: ScriptLine[] = []
  text.split(/\r?\n/).forEach((raw, i) => {
    const source = raw.trim()
    if (!source) return
    try {
      const value: unknown = JSON.parse(source)
      if (isScriptLine(value)) lines.push(value)
      else log(`Script line ${i + 1} is not a record line; skipped.`)
    } catch {
      log(`Script line ${i + 1} is not JSON; skipped.`)
    }
  })
  return lines.sort((a, b) => a.offset_ms - b.offset_ms)
}

function isScriptLine(value: unknown): value is ScriptLine {
  if (!value || typeof value !== "object") return false
  const line = value as Record<string, unknown>
  return (
    typeof line.offset_ms === "number" &&
    Number.isFinite(line.offset_ms) &&
    line.offset_ms >= 0 &&
    typeof line.table === "string" &&
    typeof line.op === "string" &&
    !!line.row &&
    typeof line.row === "object" &&
    !Array.isArray(line.row)
  )
}

/** The scripted 90 second run, copied unchanged from contract/fixtures/demo_scenario.jsonl. */
export const DEMO_SCRIPT: readonly ScriptLine[] = parseScript(scenario)
