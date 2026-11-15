/** The two claims the dashboard routes on. The backend checks them again. */
export function readClaims(token: string): { aal: "aal1" | "aal2" | null; sub: string | null } {
  try {
    const part = token.split(".")[1]
    if (!part) return { aal: null, sub: null }
    const pad = part.length % 4 === 0 ? "" : "=".repeat(4 - (part.length % 4))
    const json: unknown = JSON.parse(atob(part.replace(/-/g, "+").replace(/_/g, "/") + pad))
    if (!json || typeof json !== "object") return { aal: null, sub: null }
    const claims = json as { aal?: unknown; sub?: unknown }
    const aal = claims.aal === "aal1" || claims.aal === "aal2" ? claims.aal : null
    const sub = typeof claims.sub === "string" ? claims.sub : null
    return { aal, sub }
  } catch {
    return { aal: null, sub: null }
  }
}
