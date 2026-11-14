import * as React from "react"
import { useNavigate } from "react-router"

import CobaltToileLanding from "@/components/ui/cobalt-toile-landing"

import * as words from "@/content/landing"

/** Same-origin paths such as /sign-in stay inside the app instead of reloading the page. */
function useInAppLinks() {
  const navigate = useNavigate()
  return (e: React.MouseEvent) => {
    if (e.defaultPrevented || e.button !== 0 || e.metaKey || e.ctrlKey || e.shiftKey || e.altKey) return
    const link = (e.target as Element).closest?.("a")
    if (!link || (link.target && link.target !== "_self")) return
    const href = link.getAttribute("href")
    if (!href || !href.startsWith("/") || href.startsWith("//")) return
    e.preventDefault()
    navigate(href)
  }
}

export default function Landing() {
  const onClick = useInAppLinks()

  React.useEffect(() => {
    document.title = "Argos · keeps watch, sends word"
  }, [])

  return (
    <div onClick={onClick}>
      <CobaltToileLanding
        className="argos-landing"
        brand={words.brand}
        monogram={words.monogram}
        logo={<span className="argos-mark argos-landing-logo" aria-hidden="true" />}
        nav={words.nav}
        cta={words.cta}
        hero={words.hero}
        clients={words.clients}
        clientsLabel={words.clientsLabel}
        about={words.about}
        solutionsCopy={words.solutionsCopy}
        solutions={words.solutions}
        servicesCopy={words.servicesCopy}
        services={words.services}
        pressCopy={words.pressCopy}
        press={words.press}
        notes={words.notes}
        contactBand={words.contactBand}
        contact={words.contact}
        tagline={words.tagline}
        columns={words.columns}
        socials={[]}
        legal={words.legal}
        copyright=""
        palette="cobalt"
        theme="light"
        paletteSwitcher={false}
      />
    </div>
  )
}
