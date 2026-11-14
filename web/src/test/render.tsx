import { render } from "@testing-library/react"
import { MemoryRouter } from "react-router"

import App from "@/App"
import { createDemoAuth } from "@/auth/demo"
import type { Role } from "@/auth/types"
import { markRevealPlayed } from "@/components/argos/reveal"

export interface RenderAppOptions {
  /** Open a demo session for this role before rendering. */
  role?: Role
  /** Pretend the reveal has already played in this tab. Defaults to true. */
  revealSeen?: boolean
}

export function renderApp(path: string, { role, revealSeen = true }: RenderAppOptions = {}) {
  if (revealSeen) markRevealPlayed()
  const auth = createDemoAuth(window.sessionStorage)
  if (role) auth.openDemo(role)
  const utils = render(
    <MemoryRouter initialEntries={[path]}>
      <App auth={auth} />
    </MemoryRouter>,
  )
  return { auth, ...utils }
}
