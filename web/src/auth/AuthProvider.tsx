import * as React from "react"

import { createAuthClient } from "./client"
import { AuthContext } from "./context"
import type { AuthClient } from "./types"

export function AuthProvider({ client, children }: { client?: AuthClient; children: React.ReactNode }) {
  const [value] = React.useState(() => client ?? createAuthClient())
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}
