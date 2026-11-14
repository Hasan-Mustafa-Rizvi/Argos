import { screen, within } from "@testing-library/react"
import { describe, expect, it } from "vitest"

import { renderApp } from "./render"

/** Every default the template would print, and the strings the prompt names. None may reach the page. */
const TEMPLATE_DEFAULTS = [
  // Named by the prompt.
  "Hesper",
  "Atheneum",
  "Trusted by",
  "@example",
  "+351",
  "Almanac",
  "Subscribe",
  // Hero, about and section defaults.
  "Timeless Thinking",
  "We partner with",
  "Explore solutions",
  "Est. MCMXII",
  "Vol. I",
  "About the house",
  "counting-house",
  "Years of practice",
  "Engagements delivered",
  "Countries advised",
  "Four practices",
  "A ledger of",
  "Engagements are fixed",
  // Clients.
  "Halden Trust",
  "Corvina",
  "Museo Aurelio",
  "Northwind",
  "Atlas Mutual",
  "Verity Labs",
  "Ostra Foods",
  "Kestrel Grid",
  // Solutions and services.
  "Strategy & Narrative",
  "Markets & Expansion",
  "Brand & Reputation",
  "Infrastructure & Operations",
  "Discuss this practice",
  "Strategic Advisory",
  "Organisational Design",
  "Digital Transformation",
  "Research & Foresight",
  "Capital & Partnerships",
  "Typical length",
  // Press.
  "Latest Press",
  "Strategy Digest",
  "Ledger Review",
  "Rostrum",
  "Local Gazette",
  "Meridian Weekly",
  "Consult Quarterly",
  // Contact band and contact.
  "Let us build something",
  "Book a conversation",
  "+44",
  "London · Lisbon",
  "mailto:",
  "tel:",
  // Footer, socials and the palette switcher.
  "Designing durable strategies",
  "Our story",
  "Leadership",
  "Careers",
  "FAQs",
  "Offices",
  "Contact us",
  "Privacy Policy",
  "Terms of Service",
  "Cookie Policy",
  "All rights reserved",
  "Get started",
  "facebook",
  "instagram",
  "linkedin",
  "Printed in",
]

async function landing() {
  renderApp("/")
  return screen.findByRole("heading", { level: 1 })
}

describe("landing", () => {
  it("prints the Argos words", async () => {
    expect((await landing()).textContent).toContain("Someone to")
    expect(screen.getAllByText(/stays in the room, notices when something is wrong/).length).toBeGreaterThan(0)
  })

  it("names who made this", async () => {
    await landing()
    const section = document.querySelector('[data-sec="insights"]')
    expect(section).not.toBeNull()
    const text = section?.textContent ?? ""
    for (const name of ["Hasan Mustafa Rizvi", "Neel", "Farrell", "design, interface polish and organization"]) {
      expect(text).toContain(name)
    }
  })

  it("prints the credit line with a Credits link", async () => {
    await landing()
    const footer = screen.getByRole("contentinfo")
    expect(footer.textContent).toContain("Cobalt Toile")
    expect(footer.textContent).toContain("Kedhareswer Naidu")
    expect(footer.textContent).toContain("Glass Icon Reveal by Zanwei Guo")
    const credits = within(footer).getByRole("link", { name: "Credits" })
    expect(credits).toHaveAttribute("href", "https://github.com/Hasan-Mustafa-Rizvi/Argos#credits")
  })

  it("sends both calls to action to /sign-in", async () => {
    await landing()
    const toDashboard = screen.getAllByRole("link", { name: "Open the dashboard" })
    expect(toDashboard.length).toBeGreaterThanOrEqual(2)
    for (const link of toDashboard) expect(link).toHaveAttribute("href", "/sign-in")
  })

  it("lets nothing invented reach the page", async () => {
    await landing()
    const html = document.body.innerHTML
    const text = document.body.textContent ?? ""
    for (const phrase of TEMPLATE_DEFAULTS) {
      expect(text, phrase).not.toContain(phrase)
      expect(html, phrase).not.toContain(phrase)
    }
    expect(screen.queryByRole("textbox")).not.toBeInTheDocument()
  })
})
