/**
 * The live view reader from contract section 6. It decides. It does not draw, store, or log.
 *
 * Size is the UTF-8 length of the compact JSON of the received object, extra fields included.
 * The cut is 100000 bytes, the same cut the brain uses for "under 100 KB", so a frame the
 * brain will send is a frame this reader will take.
 */

export const FRAME_MAX_BYTES = 100_000
export const FRAME_SILENCE_MS = 5_000
export const FRAME_LONG_SIDE = 480

export interface ShownFrame {
  readonly seq: number
  readonly at: string
  readonly w: number
  readonly h: number
  readonly jpeg: string
}

export interface FrameReader {
  readonly phase: "waiting" | "live" | "stopped"
  readonly frame: ShownFrame | null
  readonly receivedAt: number | null
  /** Forgotten once the view has stopped, so a brain that counts from zero is taken at once. */
  readonly lastSeq: number | null
}

export const EMPTY_READER: FrameReader = {
  phase: "waiting",
  frame: null,
  receivedAt: null,
  lastSeq: null,
}

/** The contract object, unwrapped if the channel handed us its envelope. */
export function frameMessage(payload: unknown): unknown {
  if (!payload || typeof payload !== "object") return payload
  const obj = payload as Record<string, unknown>
  if ("jpeg" in obj || "seq" in obj) return obj
  if (obj.payload && typeof obj.payload === "object") return obj.payload
  return obj
}

export function frameBytes(value: unknown): number {
  try {
    return new TextEncoder().encode(JSON.stringify(value)).length
  } catch {
    return Number.POSITIVE_INFINITY
  }
}

function parseFrame(message: unknown): ShownFrame | null {
  if (!message || typeof message !== "object") return null
  const row = message as Record<string, unknown>
  if (!Number.isInteger(row.seq) || (row.seq as number) < 0) return null
  if (typeof row.at !== "string" || Number.isNaN(Date.parse(row.at))) return null
  if (!Number.isInteger(row.w) || !Number.isInteger(row.h)) return null
  const w = row.w as number
  const h = row.h as number
  if (w < 1 || h < 1 || Math.max(w, h) > FRAME_LONG_SIDE) return null
  if (typeof row.jpeg !== "string" || row.jpeg.length === 0) return null
  return { seq: row.seq as number, at: row.at, w, h, jpeg: row.jpeg }
}

/** Accept a frame, or return the same reader when it is dropped. */
export function offerFrame(reader: FrameReader, message: unknown, now: number): FrameReader {
  if (frameBytes(message) >= FRAME_MAX_BYTES) return reader
  const frame = parseFrame(message)
  if (!frame) return reader
  if (reader.lastSeq !== null && frame.seq < reader.lastSeq) return reader
  return { phase: "live", frame, receivedAt: now, lastSeq: frame.seq }
}

/** Five seconds from when the frame arrived, never from the frame's own `at`. */
export function silence(reader: FrameReader, now: number): FrameReader {
  if (reader.phase !== "live" || reader.receivedAt === null) return reader
  if (now - reader.receivedAt < FRAME_SILENCE_MS) return reader
  return { phase: "stopped", frame: reader.frame, receivedAt: reader.receivedAt, lastSeq: null }
}
