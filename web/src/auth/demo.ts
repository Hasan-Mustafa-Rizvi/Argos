import { isRole, ROLE_NAMES, type AuthClient, type Role, type Session } from "./types"

export const DEMO_SESSION_KEY = "argos.session"

function tabStorage(): Storage | null {
  try {
    return window.sessionStorage
  } catch {
    return null
  }
}

function demoSession(role: Role): Session {
  return Object.freeze({ role, demo: true, secondFactor: false, label: `${ROLE_NAMES[role]} (demo)` })
}

/**
 * Demo sessions only, kept in this tab's sessionStorage. It never signs anyone in with a
 * password: there are no accounts yet.
 */
export function createDemoAuth(storage: Storage | null = tabStorage()): AuthClient {
  const listeners = new Set<() => void>()
  let current = read()

  function read(): Session | null {
    try {
      const raw = storage?.getItem(DEMO_SESSION_KEY)
      if (!raw) return null
      const role: unknown = (JSON.parse(raw) as { role?: unknown } | null)?.role
      return isRole(role) ? demoSession(role) : null
    } catch {
      return null
    }
  }

  function publish(next: Session | null) {
    current = next
    listeners.forEach((listener) => listener())
  }

  return {
    getSession: () => current,
    subscribe(listener) {
      listeners.add(listener)
      return () => {
        listeners.delete(listener)
      }
    },
    async signInWithPassword() {
      return { status: "unavailable" }
    },
    openDemo(role) {
      const session = demoSession(role)
      try {
        storage?.setItem(DEMO_SESSION_KEY, JSON.stringify({ role }))
      } catch {
        // Storage can be full or blocked; the session still holds for this page.
      }
      publish(session)
      return session
    },
    async signOut() {
      try {
        storage?.removeItem(DEMO_SESSION_KEY)
      } catch {
        // Nothing stored to remove.
      }
      publish(null)
    },
  }
}
