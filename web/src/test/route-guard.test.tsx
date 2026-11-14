import { fireEvent, screen } from "@testing-library/react"
import { describe, expect, it } from "vitest"

import { renderApp } from "./render"

describe("route guard", () => {
  it("sends /dashboard with no session to /sign-in", async () => {
    renderApp("/dashboard")
    expect(await screen.findByRole("heading", { name: "Sign in" })).toBeInTheDocument()
    expect(screen.queryByTestId("dashboard")).not.toBeInTheDocument()
  })

  it.each([
    ["Open the demo as family", "family"],
    ["Open the demo as clinician", "clinician"],
  ] as const)("%s opens a %s demo session with no second factor", async (button, role) => {
    const { auth } = renderApp("/sign-in")
    fireEvent.click(await screen.findByRole("button", { name: button }))
    expect(auth.getSession()).toMatchObject({ role, demo: true, secondFactor: false })
    expect(await screen.findByTestId("dashboard")).toBeInTheDocument()
    expect(screen.getByText(role === "family" ? "Family" : "Clinician", { selector: ".argos-chip" })).toBeInTheDocument()
  })

  it("applies again after sign out", async () => {
    const { auth, unmount } = renderApp("/dashboard", { role: "family" })
    fireEvent.click(await screen.findByRole("button", { name: "Sign out" }))
    expect(await screen.findByRole("heading", { name: "Sign in" })).toBeInTheDocument()
    expect(auth.getSession()).toBeNull()
    unmount()

    renderApp("/dashboard")
    expect(await screen.findByRole("heading", { name: "Sign in" })).toBeInTheDocument()
  })

  it("sends /sign-in with a session to /dashboard", async () => {
    renderApp("/sign-in", { role: "clinician" })
    expect(await screen.findByTestId("dashboard")).toBeInTheDocument()
    expect(screen.queryByRole("heading", { name: "Sign in" })).not.toBeInTheDocument()
  })

  it("does not pretend to sign anyone in with a password", async () => {
    const { auth } = renderApp("/sign-in")
    fireEvent.change(await screen.findByLabelText("Email"), { target: { value: "someone" } })
    fireEvent.click(screen.getByRole("button", { name: "Sign in" }))
    expect(await screen.findByText(/Accounts are not open yet/)).toBeInTheDocument()
    expect(auth.getSession()).toBeNull()
  })
})
