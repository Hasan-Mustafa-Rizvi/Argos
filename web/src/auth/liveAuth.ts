import { readClaims } from "@/live/claims"
import type { Gateway } from "@/live/ports"

import { clearDemo, demoSession, readDemo, tabStorage, writeDemo } from "./demo"
import type { AuthClient, ChallengeSession, EnrolResult, ReadySession, Role, Session, SignInResult, UnlinkedSession } from "./types"

const PASSWORD_NO = "That email or password is not right."
const CODE_NO = "That code is not right. Try again."
const TRY_AGAIN = "Something went wrong. Try again."
const UNREACHABLE = "Argos cannot be reached just now. Try again."

/**
 * Real sign-in. The role comes from the membership row, and only after the second factor.
 * A demo session and a real session are never both current: opening the demo ends the real
 * session, and signing in for real ends the demo.
 *
 * The gateway is injected in tests. In the app it is loaded on prepare, and only then.
 */
export function createLiveAuth(injected?: Gateway, storage: Storage | null = tabStorage()): AuthClient {
  const listeners = new Set<() => void>()
  let current: Session | null = readDemo(storage)
  let ready = current?.kind === "demo"
  let gateway: Gateway | null = injected ?? null
  let userId: string | null = null
  let factorId: string | null = null
  let enrolment: Promise<EnrolResult> | null = null
  let signingOut: Promise<void> = Promise.resolve()
  let generation = 0
  let preparing: Promise<void> | null = null
  let markPrepared: (() => void) | null = null

  function publish(next: Session | null) {
    current = next
    listeners.forEach((listener) => listener())
  }

  function markReady() {
    const was = ready
    ready = true
    if (!was) listeners.forEach((listener) => listener())
    markPrepared?.()
    markPrepared = null
  }

  async function resolveGateway(): Promise<Gateway> {
    if (gateway) return gateway
    const { sharedGateway } = await import("@/live/shared")
    gateway = await sharedGateway()
    return gateway
  }

  async function settle(event: "signed-in" | "signed-out" | "token", token: string | null) {
    const gen = ++generation
    if (current?.kind === "demo" && readDemo(storage)) {
      markReady()
      return
    }
    if (!token || event === "signed-out") {
      const demo = readDemo(storage)
      if (demo) {
        publish(demo)
        markReady()
        return
      }
      try {
        const port = await resolveGateway()
        if (gen !== generation) return
        const still = await port.currentToken()
        if (gen !== generation) return
        if (still) {
          await settle("signed-in", still)
          return
        }
      } catch {
        // Fall through and clear. A missing session is a sign-out.
      }
      if (gen !== generation) return
      userId = null
      factorId = null
      enrolment = null
      if (current) publish(null)
      markReady()
      return
    }

    const claims = readClaims(token)
    if (claims.aal === "aal2" && current?.kind === "ready" && claims.sub === userId && event !== "signed-in") {
      try {
        const port = await resolveGateway()
        if (gen !== generation) return
        await port.authorize()
      } catch {
        // The next join waits on authorize and will say so if this stays failed.
      }
      markReady()
      return
    }
    if (claims.aal === "aal2" && current?.kind === "ready" && claims.sub === userId && event === "signed-in") {
      markReady()
      return
    }

    let port: Gateway
    try {
      port = await resolveGateway()
    } catch {
      markReady()
      return
    }
    if (gen !== generation) return

    if (claims.aal !== "aal2") {
      if (current?.kind === "challenge" && claims.sub === userId && event === "signed-in") {
        markReady()
        return
      }
      try {
        const factors = await port.listFactors()
        if (gen !== generation) return
        factorId = factors.verified[0] ?? null
        userId = claims.sub
        const next: ChallengeSession = Object.freeze({
          kind: "challenge",
          demo: false,
          secondFactor: false,
          step: factors.verified.length ? "code" : "enrol",
        })
        publish(next)
      } catch {
        if (gen !== generation) return
        publish(null)
      }
      markReady()
      return
    }

    try {
      await port.authorize()
      if (gen !== generation) return
      const member = await port.loadMember()
      if (gen !== generation) return
      userId = claims.sub
      factorId = null
      enrolment = null
      if (!member) {
        const next: UnlinkedSession = Object.freeze({ kind: "unlinked", demo: false, secondFactor: true })
        publish(next)
      } else {
        const next: ReadySession = Object.freeze({
          kind: "ready",
          role: member.role,
          demo: false,
          secondFactor: true,
          label: member.label,
          deviceId: member.deviceId,
        })
        publish(next)
      }
    } catch {
      if (gen !== generation) return
    }
    markReady()
  }

  function resultOf(session: Session | null): SignInResult {
    if (session?.kind === "ready") return { status: "signed-in" }
    if (session?.kind === "unlinked") return { status: "unlinked" }
    if (session?.kind === "challenge") return { status: "second-factor" }
    return { status: "error", message: TRY_AGAIN }
  }

  return {
    getSession: () => current,
    isReady: () => ready,
    subscribe(listener) {
      listeners.add(listener)
      return () => {
        listeners.delete(listener)
      }
    },
    prepare() {
      if (!preparing) {
        preparing = new Promise<void>((resolve) => {
          markPrepared = resolve
          void resolveGateway()
            .then((port) => {
              port.subscribeAuth((event, token) => {
                void settle(event, token)
              })
              if (current?.kind === "demo") markReady()
            })
            .catch(() => {
              markReady()
            })
        })
      }
      return preparing
    },
    async signInWithPassword(email, password) {
      await signingOut
      clearDemo(storage)
      if (current?.kind === "demo") publish(null)
      enrolment = null
      let port: Gateway
      try {
        port = await resolveGateway()
      } catch {
        return { status: "error", message: UNREACHABLE }
      }
      const signed = await port.signInWithPassword(email, password)
      if (!signed.ok) {
        return { status: "error", message: signed.reason === "unreachable" ? UNREACHABLE : PASSWORD_NO }
      }
      await settle("signed-in", signed.token)
      return resultOf(current)
    },
    async verifyCode(code) {
      if (current?.kind !== "challenge") return { status: "error", message: CODE_NO }
      let port: Gateway
      try {
        port = await resolveGateway()
      } catch {
        return { status: "error", message: UNREACHABLE }
      }
      let id = factorId
      if (!id) {
        try {
          const factors = await port.listFactors()
          id = factors.verified[0] ?? null
        } catch {
          return { status: "error", message: TRY_AGAIN }
        }
      }
      if (!id) return { status: "error", message: TRY_AGAIN }
      const checked = await port.verify(id, code)
      if (!checked.ok) return { status: "error", message: CODE_NO }
      try {
        await port.authorize()
      } catch {
        return { status: "error", message: UNREACHABLE }
      }
      await settle("signed-in", checked.token)
      if (current?.kind === "challenge") return { status: "error", message: UNREACHABLE }
      return resultOf(current)
    },
    beginEnrolment() {
      if (enrolment) return enrolment
      enrolment = (async (): Promise<EnrolResult> => {
        try {
          const port = await resolveGateway()
          const record = await port.enroll()
          factorId = record.factorId
          return { status: "enrol", qr: record.qr, secret: record.secret }
        } catch {
          enrolment = null
          return { status: "error", message: TRY_AGAIN }
        }
      })()
      return enrolment
    },
    openDemo(role: Role) {
      const session = demoSession(role)
      writeDemo(storage, role)
      userId = null
      factorId = null
      enrolment = null
      publish(session)
      ready = true
      if (gateway) {
        const port = gateway
        signingOut = port.signOut().then(
          () => undefined,
          () => undefined,
        )
      }
      return session
    },
    async signOut() {
      clearDemo(storage)
      userId = null
      factorId = null
      enrolment = null
      publish(null)
      if (!gateway) return
      const port = gateway
      try {
        await port.closeChannels()
      } catch {
        // The channels are dropped on the way out either way.
      }
      signingOut = port.signOut().then(
        () => undefined,
        () => undefined,
      )
      await signingOut
    },
  }
}
