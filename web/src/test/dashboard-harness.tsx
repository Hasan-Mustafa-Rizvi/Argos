import { act, render } from "@testing-library/react"
import { MemoryRouter } from "react-router"
import { vi } from "vitest"

import { AuthProvider } from "@/auth/AuthProvider"
import { createDemoAuth } from "@/auth/demo"
import type { Role } from "@/auth/types"
import { DashboardScreen } from "@/components/dashboard/DashboardScreen"
import { BASE_TIME, type ScriptLine } from "@/data/contract"
import { DataProvider } from "@/data/DataProvider"
import { createReplaySource } from "@/data/replay"

export const DEVICE_ID = "a0000000-0000-4000-8000-000000000001"

/** ISO time `seconds` after the fixture's base time. */
export function at(seconds: number) {
  return new Date(BASE_TIME + seconds * 1000).toISOString()
}

export function deviceLine(offsetMs: number, state: string, extra: Record<string, unknown> = {}): ScriptLine {
  return {
    offset_ms: offsetMs,
    table: "devices",
    op: "upsert",
    row: {
      id: DEVICE_ID,
      name: "Argos",
      person_label: "Eleni",
      state,
      last_seen_at: at(offsetMs / 1000),
      fw: "0.1.0",
      caps: [],
      ...extra,
    },
  }
}

export interface DashboardHarnessOptions {
  role: Role
  lines?: readonly ScriptLine[]
  path?: string
  log?: (message: string) => void
}

/** The dashboard on a replay that the test drives with fake timers. */
export function renderDashboard({ role, lines, path = "/dashboard", log = () => {} }: DashboardHarnessOptions) {
  const auth = createDemoAuth(window.sessionStorage)
  const opened = auth.openDemo(role)
  if (opened.kind !== "demo") throw new Error("A demo session was not opened.")
  const session = opened
  const source = createReplaySource({ role, label: session.label, lines, log })
  const utils = render(
    <MemoryRouter initialEntries={[path]}>
      <AuthProvider client={auth}>
        <DataProvider session={session} source={source}>
          <DashboardScreen />
        </DataProvider>
      </AuthProvider>
    </MemoryRouter>,
  )
  return { ...utils, source, session, auth }
}

/** Moves the fake clock on, letting React render what changed. */
export function advance(ms: number) {
  act(() => {
    vi.advanceTimersByTime(ms)
  })
}
