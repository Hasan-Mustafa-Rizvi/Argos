import * as React from "react"

import type { Session } from "@/auth/types"

import { DataContext } from "./context"
import { createDataSource } from "./create"
import type { DataSource } from "./source"

export interface DataProviderProps {
  session: Session
  /** A source to use instead of the one the session would get. */
  source?: DataSource
  children: React.ReactNode
}

export function DataProvider({ session, source, children }: DataProviderProps) {
  const [value] = React.useState(() => source ?? createDataSource(session))

  // Before paint, so the first frame already shows the device rather than an empty store.
  React.useLayoutEffect(() => {
    value.start()
    return () => value.stop()
  }, [value])

  return <DataContext.Provider value={value}>{children}</DataContext.Provider>
}
