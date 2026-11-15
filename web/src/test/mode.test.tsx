import { fireEvent, render, screen } from "@testing-library/react"
import { MemoryRouter } from "react-router"
import { afterEach, describe, expect, it, vi } from "vitest"

import App from "@/App"
import { clientModuleLoaded } from "@/live/load"

function renderDefault(path: string) {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <App />
    </MemoryRouter>,
  )
}

afterEach(() => {
  vi.unstubAllEnvs()
  vi.unstubAllGlobals()
})

function blockNetwork() {
  const fetchSpy = vi.fn(() => {
    throw new Error("network")
  })
  vi.stubGlobal("fetch", fetchSpy)
  vi.stubGlobal(
    "WebSocket",
    class {
      constructor() {
        throw new Error("network")
      }
    },
  )
  return fetchSpy
}

describe("rule 6", () => {
  it("stays on the demo when the settings are missing, and never loads the client", async () => {
    vi.stubEnv("VITE_DATA_MODE", "live")
    vi.stubEnv("VITE_SUPABASE_URL", "")
    vi.stubEnv("VITE_SUPABASE_PUBLISHABLE_KEY", "")
    const fetchSpy = blockNetwork()
    renderDefault("/sign-in")
    fireEvent.click(await screen.findByRole("button", { name: "Sign in" }))
    expect(await screen.findByText(/Accounts are not open yet/)).toBeInTheDocument()
    expect(clientModuleLoaded()).toBe(false)
    expect(fetchSpy).not.toHaveBeenCalled()
  })

  it("stays on the demo when the settings are present but the mode is not live", async () => {
    vi.stubEnv("VITE_DATA_MODE", "replay")
    vi.stubEnv("VITE_SUPABASE_URL", "http://127.0.0.1:9")
    vi.stubEnv("VITE_SUPABASE_PUBLISHABLE_KEY", "publishable-placeholder")
    const fetchSpy = blockNetwork()
    renderDefault("/sign-in")
    fireEvent.click(await screen.findByRole("button", { name: "Sign in" }))
    expect(await screen.findByText(/Accounts are not open yet/)).toBeInTheDocument()
    expect(clientModuleLoaded()).toBe(false)
    expect(fetchSpy).not.toHaveBeenCalled()
  })
})
