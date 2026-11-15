import * as React from "react"
import { Navigate, useLocation } from "react-router"

import { NotLinked } from "./NotLinked"
import { useAuthClient, useAuthReady, useSession } from "./context"

/**
 * While a stored session is being read, show the paper and nothing else, so the form and
 * the dashboard never flash.
 */
export function SessionGate({ children }: { children: React.ReactNode }) {
  const ready = useAuthReady()
  const auth = useAuthClient()
  const location = useLocation()
  const gated = location.pathname === "/sign-in" || location.pathname === "/dashboard"

  React.useEffect(() => {
    if (gated) void auth.prepare()
  }, [gated, auth])

  if (gated && !ready) return <div style={{ minHeight: "100dvh", background: "var(--paper)" }} />
  return children
}

/** Pages behind sign-in. A session that still owes the second step goes back to it. */
export function RequireSession({ children }: { children: React.ReactNode }) {
  const session = useSession()
  if (!session || session.kind === "challenge") return <Navigate to="/sign-in" replace />
  if (session.kind === "unlinked") return <NotLinked />
  return children
}

/** Sign-in itself. A demo or a finished real session goes to the dashboard. */
export function RedirectIfSignedIn({ children }: { children: React.ReactNode }) {
  const session = useSession()
  if (session?.kind === "demo" || session?.kind === "ready") return <Navigate to="/dashboard" replace />
  return children
}
