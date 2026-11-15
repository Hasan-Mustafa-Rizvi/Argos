import { isRole, ROLE_NAMES, type AuthClient, type DemoSession, type Role, type Session } from "./types"

export const DEMO_SESSION_KEY = "argos.session"

export function tabStorage(): Storage | null {
  try {
    return window.sessionStorage
  } catch {
    return null
  }
}

export function demoSession(role: Role): DemoSession {
  return Object.freeze({ kind: "demo", role, demo: true, secondFactor: false, label: `${ROLE_NAMES[role]} (demo)` })
}

export function readDemo(storage: Storage | null): DemoSession | null {
  try {
    const raw = storage?.getItem(DEMO_SESSION_KEY)
    if (!raw) return null
    const role: unknown = (JSON.parse(raw) as { role?: unknown } | null)?.role
    return isRole(role) ? demoSession(role) : null
  } catch {
    return null
  }
}

export function writeDemo(storage: Storage | null, role: Role) {
  try {
    storage?.setItem(DEMO_SESSION_KEY, JSON.stringify({ role }))
  } catch {
    // Storage can be full or blocked. The session still holds for this page.
  }
}

export function clearDemo(storage: Storage | null) {
  try {
    storage?.removeItem(DEMO_SESSION_KEY)
  } catch {
    // Nothing stored to remove.
  }
}

/**
 * Demo sessions only, kept in this tab's sessionStorage. It never signs anyone in with a
 * password: there are no accounts in this mode.
 */
export function createDemoAuth(storage: Storage | null = tabStorage()): AuthClient {
  const listeners = new Set<() => void>()
  let current: Session | null = readDemo(storage)

  function publish(next: Session | null) {
    current = next
    listeners.forEach((listener) => listener())
  }

  return {
    getSession: () => current,
    isReady: () => true,
    subscribe(listener) {
      listeners.add(listener)
      return () => {
        listeners.delete(listener)
      }
    },
    async prepare() {},
    async signInWithPassword() {
      return { status: "unavailable" }
    },
    async verifyCode() {
      return { status: "unavailable" }
    },
    async beginEnrolment() {
      return { status: "error", message: "Accounts are not open yet." }
    },
    openDemo(role) {
      const session = demoSession(role)
      writeDemo(storage, role)
      publish(session)
      return session
    },
    async signOut() {
      clearDemo(storage)
      publish(null)
    },
  }
}
