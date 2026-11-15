import * as React from "react"

import type { DashboardView, DataSource } from "./source"

export const DataContext = React.createContext<DataSource | null>(null)

export function useDataSource(): DataSource {
  const source = React.useContext(DataContext)
  if (!source) throw new Error("useDataSource needs a DataProvider above it")
  return source
}

/** The records this session may see, as they stand now. */
export function useDashboardView(): DashboardView {
  const source = useDataSource()
  return React.useSyncExternalStore(source.subscribe, source.getView, source.getView)
}
