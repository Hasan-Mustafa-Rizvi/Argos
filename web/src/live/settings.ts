/** Live mode needs both settings and the mode. Anything else is today's demo site. */
export function liveSettings(): { url: string; key: string } | null {
  const mode = import.meta.env.VITE_DATA_MODE
  const url = import.meta.env.VITE_SUPABASE_URL?.trim()
  const key = import.meta.env.VITE_SUPABASE_PUBLISHABLE_KEY?.trim()
  if (mode !== "live" || !url || !key) return null
  return { url, key }
}

export function liveConfigured(): boolean {
  return liveSettings() !== null
}
