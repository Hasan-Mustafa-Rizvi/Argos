import * as React from "react"

import type { AuthClient, Session } from "./types"

export const AuthContext = React.createContext<AuthClient | null>(null)

export function useAuthClient(): AuthClient {
  const client = React.useContext(AuthContext)
  if (!client) throw new Error("useAuthClient needs an AuthProvider above it")
  return client
}

/** The current session, or null when nobody is signed in. */
export function useSession(): Session | null {
  const client = useAuthClient()
  return React.useSyncExternalStore(client.subscribe, client.getSession, client.getSession)
}
