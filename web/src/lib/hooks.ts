import * as React from "react"

function subscribeMedia(query: string) {
  return (onChange: () => void) => {
    if (typeof window.matchMedia !== "function") return () => {}
    const mq = window.matchMedia(query)
    mq.addEventListener?.("change", onChange)
    return () => mq.removeEventListener?.("change", onChange)
  }
}

function useMediaQuery(query: string): boolean {
  const subscribe = React.useMemo(() => subscribeMedia(query), [query])
  return React.useSyncExternalStore(
    subscribe,
    () => typeof window.matchMedia === "function" && window.matchMedia(query).matches,
    () => false,
  )
}

export function usePrefersReducedMotion(): boolean {
  return useMediaQuery("(prefers-reduced-motion: reduce)")
}

/** Counts the changes of `key`: one step for every new report. */
export function useBeat(key: string | null | undefined): number {
  const [seen, setSeen] = React.useState({ key, beat: 0 })
  if (seen.key !== key) {
    const next = { key, beat: seen.beat + 1 }
    setSeen(next)
    return next.beat
  }
  return seen.beat
}

/** The current time, refreshed every `everyMs`. */
export function useNow(everyMs = 1000): number {
  const [now, setNow] = React.useState(() => Date.now())
  React.useEffect(() => {
    const id = setInterval(() => setNow(Date.now()), everyMs)
    return () => clearInterval(id)
  }, [everyMs])
  return now
}
