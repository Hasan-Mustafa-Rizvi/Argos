import type { Role } from "@/auth/types"

export type AuthEvent = "signed-in" | "signed-out" | "token"

export interface MemberRecord {
  readonly deviceId: string
  readonly role: Role
  readonly label: string
}

export interface EnrolmentRecord {
  readonly factorId: string
  readonly qr: string
  readonly secret: string
}

export type PasswordResult =
  | { readonly ok: true; readonly token: string }
  | { readonly ok: false; readonly reason: "credentials" | "unreachable" }

export type VerifyResult = { readonly ok: true; readonly token: string } | { readonly ok: false }

export interface LiveChange {
  readonly table: string
  readonly event: "INSERT" | "UPDATE" | "DELETE"
  readonly row: Readonly<Record<string, unknown>>
}

export interface LiveChannel {
  onChange(table: string, columns: readonly string[], onRow: (change: LiveChange) => void): void
  onBroadcast(event: string, onMessage: (payload: unknown) => void): void
  subscribe(onStatus: (status: "joined" | "dropped") => void): void
  leave(): Promise<void>
}

/**
 * The narrow surface the auth client and the live source talk to. Tests pass a fake.
 * The real one is in gateway.ts and is loaded only in live mode.
 */
export interface Gateway {
  subscribeAuth(handler: (event: AuthEvent, token: string | null) => void): () => void
  signInWithPassword(email: string, password: string): Promise<PasswordResult>
  signOut(): Promise<void>
  /** The token the client holds now, or null. Used to ignore a sign-out that lost the race. */
  currentToken(): Promise<string | null>
  listFactors(): Promise<{ verified: readonly string[]; unverified: readonly string[] }>
  enroll(): Promise<EnrolmentRecord>
  verify(factorId: string, code: string): Promise<VerifyResult>
  loadMember(): Promise<MemberRecord | null>
  /** Hand the current session token to Realtime and wait until it is set. */
  authorize(): Promise<void>
  closeChannels(): Promise<void>
  openChannel(topic: string): LiveChannel
  loadDevice(deviceId: string): Promise<Record<string, unknown> | null>
  loadIncidents(deviceId: string, columns: readonly string[]): Promise<Record<string, unknown>[]>
  loadEvents(deviceId: string): Promise<Record<string, unknown>[]>
  loadReadings(deviceId: string): Promise<Record<string, unknown>[]>
  loadIncident(id: string, columns: readonly string[]): Promise<Record<string, unknown> | null>
  acknowledge(
    id: string,
    patch: { status: "acknowledged"; acknowledged_by: string; acknowledged_at: string },
  ): Promise<string | null>
  downloadSnapshot(path: string): Promise<Blob | null>
}
