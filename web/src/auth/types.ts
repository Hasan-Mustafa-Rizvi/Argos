export type Role = "family" | "clinician"

export const ROLES: readonly Role[] = ["family", "clinician"]

export const ROLE_NAMES: Readonly<Record<Role, string>> = {
  family: "Family",
  clinician: "Clinician",
}

export function isRole(value: unknown): value is Role {
  return value === "family" || value === "clinician"
}

/** What a signed-in session answers. Nobody signed in is `null`. */
export interface Session {
  readonly role: Role
  /** A demo session plays the scripted run and never reads live records or the live view. */
  readonly demo: boolean
  /** Whether this session has passed its second factor. */
  readonly secondFactor: boolean
  /** How this session is named when it acknowledges an incident. */
  readonly label: string
}

export type SignInResult =
  | { readonly status: "signed-in" }
  | { readonly status: "second-factor" }
  /** This build has no real accounts. */
  | { readonly status: "unavailable" }
  | { readonly status: "error"; readonly message: string }

/**
 * The one auth interface pages use. The demo implementation lives in demo.ts; a Supabase
 * implementation can replace it in client.ts without touching any page.
 */
export interface AuthClient {
  getSession(): Session | null
  subscribe(listener: () => void): () => void
  signInWithPassword(email: string, password: string): Promise<SignInResult>
  openDemo(role: Role): Session
  signOut(): Promise<void>
}
