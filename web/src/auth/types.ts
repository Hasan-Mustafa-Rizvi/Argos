export type Role = "family" | "clinician"

export const ROLES: readonly Role[] = ["family", "clinician"]

export const ROLE_NAMES: Readonly<Record<Role, string>> = {
  family: "Family",
  clinician: "Clinician",
}

export function isRole(value: unknown): value is Role {
  return value === "family" || value === "clinician"
}

/** A demo session plays the scripted run and never reads live records or the live view. */
export interface DemoSession {
  readonly kind: "demo"
  readonly role: Role
  readonly demo: true
  readonly secondFactor: false
  readonly label: string
}

/** Signed in with a password, still owing the authenticator. The role is not known yet. */
export interface ChallengeSession {
  readonly kind: "challenge"
  readonly demo: false
  readonly secondFactor: false
  readonly step: "enrol" | "code"
}

/** The second factor passed, and this account has no membership row. */
export interface UnlinkedSession {
  readonly kind: "unlinked"
  readonly demo: false
  readonly secondFactor: true
}

/** Fully signed in, past the second factor, linked to one dog. */
export interface ReadySession {
  readonly kind: "ready"
  readonly role: Role
  readonly demo: false
  readonly secondFactor: true
  readonly label: string
  readonly deviceId: string
}

/** Nobody signed in is `null`. */
export type Session = DemoSession | ChallengeSession | UnlinkedSession | ReadySession

/** A session the dashboard can render. */
export type DashboardSession = DemoSession | ReadySession

export function isDashboardSession(session: Session | null): session is DashboardSession {
  return session?.kind === "demo" || session?.kind === "ready"
}

export type SignInResult =
  | { readonly status: "signed-in" }
  | { readonly status: "second-factor" }
  | { readonly status: "unlinked" }
  | { readonly status: "unavailable" }
  | { readonly status: "error"; readonly message: string }

export type EnrolResult =
  | { readonly status: "enrol"; readonly qr: string; readonly secret: string }
  | { readonly status: "error"; readonly message: string }

/**
 * The one auth interface pages use. The demo implementation lives in demo.ts. The live
 * one is in liveAuth.ts and is used only when the site is in live mode.
 */
export interface AuthClient {
  getSession(): Session | null
  /** False while a stored real session is being read. The demo client is always ready. */
  isReady(): boolean
  subscribe(listener: () => void): () => void
  /** Restores a stored session. Safe to call twice. */
  prepare(): Promise<void>
  signInWithPassword(email: string, password: string): Promise<SignInResult>
  verifyCode(code: string): Promise<SignInResult>
  /** Safe to call twice. A second call while the first is held returns the same factor. */
  beginEnrolment(): Promise<EnrolResult>
  openDemo(role: Role): Session
  signOut(): Promise<void>
}
