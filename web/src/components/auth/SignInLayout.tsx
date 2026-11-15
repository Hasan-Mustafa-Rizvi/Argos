import type * as React from "react"
import { Link } from "react-router"

import { ArgosMark } from "@/components/argos/ArgosMark"

/** The sign-in page: the form on paper, the night watch plate beside it. */
export function SignInLayout({ children }: { children: React.ReactNode }) {
  return (
    <div className="argos-signin">
      <main className="argos-signin-side">
        <div className="argos-signin-column">
          <Link to="/" className="argos-signin-mark" aria-label="Argos, back to the landing page">
            <ArgosMark variant="stacked" size={112} />
          </Link>
          {children}
        </div>
      </main>
      <aside className="argos-signin-plate">
        <div className="argos-signin-face">
          <span className="argos-signin-drawing" role="img" aria-label="Argos" />
        </div>
      </aside>
    </div>
  )
}
