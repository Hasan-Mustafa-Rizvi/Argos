import type * as React from "react"
import { Navigate } from "react-router"

import { useSession } from "./context"

/** Pages behind sign-in. Without a session the visitor lands on /sign-in. */
export function RequireSession({ children }: { children: React.ReactNode }) {
  const session = useSession()
  if (!session) return <Navigate to="/sign-in" replace />
  return children
}

/** Sign-in itself. Someone already signed in goes straight to the dashboard. */
export function RedirectIfSignedIn({ children }: { children: React.ReactNode }) {
  const session = useSession()
  if (session) return <Navigate to="/dashboard" replace />
  return children
}
