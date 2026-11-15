import { fireEvent, render, screen } from "@testing-library/react"
import { MemoryRouter } from "react-router"
import { describe, expect, it } from "vitest"

import App from "@/App"
import { DEMO_SESSION_KEY } from "@/auth/demo"
import { createLiveAuth } from "@/auth/liveAuth"
import { markRevealPlayed } from "@/components/argos/reveal"

import { fakeGateway, fakeToken } from "./fake-gateway"

const DASH = /\u2014|\u2013/

function renderLive(path: string, gateway = fakeGateway()) {
  markRevealPlayed()
  const auth = createLiveAuth(gateway.gateway)
  const utils = render(
    <MemoryRouter initialEntries={[path]}>
      <App auth={auth} />
    </MemoryRouter>,
  )
  return { ...utils, auth, ...gateway }
}

describe("rule 2", () => {
  it("sends a session that still owes the second step to that step, not the dashboard", async () => {
    const fake = fakeGateway()
    fake.state.token = fakeToken("aal1")
    fake.state.verified = ["factor-verified"]
    renderLive("/dashboard", fake)
    expect(await screen.findByLabelText("Authenticator code")).toBeInTheDocument()
    expect(screen.queryByTestId("dashboard")).not.toBeInTheDocument()
    expect(fake.state.order.some((step) => step.startsWith("channel:"))).toBe(false)
  })

  it("shows the not-linked sentence when the second factor passed and no row came back", async () => {
    const fake = fakeGateway()
    fake.state.token = fakeToken("aal2")
    renderLive("/dashboard", fake)
    expect(await screen.findByText("This account is not linked to a dog yet.")).toBeInTheDocument()
    expect(screen.getByRole("button", { name: "Sign out" })).toBeInTheDocument()
    expect(screen.queryByTestId("dashboard")).not.toBeInTheDocument()
  })

  it("shows the role from the membership row", async () => {
    const fake = fakeGateway()
    fake.state.token = fakeToken("aal2")
    fake.state.members = [{ deviceId: "dog-1", role: "clinician", label: "Nurse" }]
    renderLive("/dashboard", fake)
    expect(await screen.findByText("Clinician", { selector: ".argos-chip" })).toBeInTheDocument()
    expect(screen.queryByText("Family", { selector: ".argos-chip" })).not.toBeInTheDocument()
  })
})

describe("enrolment and challenge", () => {
  it("enrols, then a wrong code can be tried again, and the dashboard shows the row's role", async () => {
    const fake = fakeGateway()
    fake.state.members = [{ deviceId: "dog-1", role: "family", label: "Daughter" }]
    renderLive("/sign-in", fake)
    fireEvent.change(await screen.findByLabelText("Email"), { target: { value: "person@example.com" } })
    fireEvent.change(screen.getByLabelText("Password"), { target: { value: "anything" } })
    fireEvent.click(screen.getByRole("button", { name: "Sign in" }))

    expect(await screen.findByText("SETUP1")).toBeInTheDocument()
    const code = screen.getByLabelText("Authenticator code")
    fireEvent.change(code, { target: { value: "000000" } })
    fireEvent.click(screen.getByRole("button", { name: "Check code" }))
    expect(await screen.findByRole("alert")).toHaveTextContent("That code is not right. Try again.")
    expect(screen.getByLabelText("Authenticator code")).toBeEnabled()

    fireEvent.change(screen.getByLabelText("Authenticator code"), { target: { value: "123456" } })
    fireEvent.click(screen.getByRole("button", { name: "Check code" }))
    expect(await screen.findByText("Family", { selector: ".argos-chip" })).toBeInTheDocument()
    expect(document.body.innerHTML).not.toMatch(DASH)
  })

  it("does not enrol twice while the first factor is held, and a fresh start clears the unfinished one", async () => {
    // The fake copies the backend: enrol creates one unverified factor, and starting
    // again removes unverified factors before creating one new one.
    const fake = fakeGateway()
    const auth = createLiveAuth(fake.gateway)
    const [first, second] = await Promise.all([auth.beginEnrolment(), auth.beginEnrolment()])
    expect(first).toEqual(second)
    expect(fake.state.enrolls).toBe(1)
    expect(fake.state.unverified).toEqual(["factor-1"])

    const again = createLiveAuth(fake.gateway)
    const next = await again.beginEnrolment()
    expect(next.status).toBe("enrol")
    expect(fake.state.enrolls).toBe(2)
    expect(fake.state.unverified).toEqual(["factor-2"])
  })

  it("a verified authenticator asks for a code and lands on the clinician dashboard", async () => {
    const fake = fakeGateway()
    fake.state.verified = ["factor-verified"]
    fake.state.members = [{ deviceId: "dog-1", role: "clinician", label: "Nurse" }]
    renderLive("/sign-in", fake)
    fireEvent.change(await screen.findByLabelText("Email"), { target: { value: "person@example.com" } })
    fireEvent.change(screen.getByLabelText("Password"), { target: { value: "anything" } })
    fireEvent.click(screen.getByRole("button", { name: "Sign in" }))
    expect(await screen.findByLabelText("Authenticator code")).toBeInTheDocument()
    expect(screen.queryByText(/SETUP/)).not.toBeInTheDocument()
    fireEvent.change(screen.getByLabelText("Authenticator code"), { target: { value: "123456" } })
    fireEvent.click(screen.getByRole("button", { name: "Check code" }))
    expect(await screen.findByText("Clinician", { selector: ".argos-chip" })).toBeInTheDocument()
  })
})

describe("one session at a time", () => {
  it("opening the demo ends the real session, and signing in for real ends the demo", async () => {
    const fake = fakeGateway()
    fake.state.token = fakeToken("aal2")
    fake.state.members = [{ deviceId: "dog-1", role: "family", label: "Daughter" }]
    const { auth } = renderLive("/dashboard", fake)
    expect(await screen.findByText("Family", { selector: ".argos-chip" })).toBeInTheDocument()

    const demo = auth.openDemo("clinician")
    expect(demo.kind).toBe("demo")
    expect(fake.state.signOuts).toBe(1)
    expect(auth.getSession()).toMatchObject({ kind: "demo", role: "clinician" })

    await auth.signInWithPassword("person@example.com", "anything")
    expect(auth.getSession()?.kind).not.toBe("demo")
    expect(window.sessionStorage.getItem(DEMO_SESSION_KEY)).toBeNull()
  })
})

describe("sign out", () => {
  it("closes the channels and leaves no session", async () => {
    const fake = fakeGateway()
    fake.state.token = fakeToken("aal2")
    fake.state.members = [{ deviceId: "dog-1", role: "family", label: "Daughter" }]
    const { auth } = renderLive("/dashboard", fake)
    expect(await screen.findByRole("button", { name: "Sign out" })).toBeInTheDocument()
    fireEvent.click(screen.getByRole("button", { name: "Sign out" }))
    expect(await screen.findByRole("heading", { name: "Sign in" })).toBeInTheDocument()
    expect(auth.getSession()).toBeNull()
    expect(fake.state.closed).toBeGreaterThan(0)
    expect(fake.state.token).toBeNull()
  })
})

describe("a wrong password", () => {
  it("reads the same for a rejected sign-in, with no backend text", async () => {
    const fake = fakeGateway()
    fake.state.password = "credentials"
    renderLive("/sign-in", fake)
    fireEvent.click(await screen.findByRole("button", { name: "Sign in" }))
    expect(await screen.findByRole("alert")).toHaveTextContent("That email or password is not right.")
    expect(document.body.innerHTML).not.toMatch(DASH)
  })
})
