import * as React from "react"
import { Eye, EyeOff } from "lucide-react"
import { Link, useNavigate } from "react-router"

import { ArgosMark } from "@/components/argos/ArgosMark"
import { DitherScene } from "@/components/argos/DitherScene"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { useAuthClient } from "@/auth/context"
import type { Role } from "@/auth/types"

const NOT_YET =
  "Accounts are not open yet. They arrive in a later build. To look around now, open the demo below."

export default function SignIn() {
  const auth = useAuthClient()
  const navigate = useNavigate()
  const [email, setEmail] = React.useState("")
  const [password, setPassword] = React.useState("")
  const [showPassword, setShowPassword] = React.useState(false)
  const [message, setMessage] = React.useState("")
  const [busy, setBusy] = React.useState(false)

  React.useEffect(() => {
    document.title = "Sign in · Argos"
  }, [])

  async function submit(e: React.FormEvent) {
    e.preventDefault()
    setBusy(true)
    const result = await auth.signInWithPassword(email.trim(), password)
    setBusy(false)
    if (result.status === "signed-in") navigate("/dashboard", { replace: true })
    else if (result.status === "error") setMessage(result.message)
    else if (result.status === "unavailable") setMessage(NOT_YET)
  }

  function openDemo(role: Role) {
    auth.openDemo(role)
    navigate("/dashboard", { replace: true })
  }

  return (
    <div className="argos-signin">
      <main className="argos-signin-side">
        <div className="argos-signin-column">
          <Link to="/" className="argos-rise argos-signin-mark" aria-label="Argos, back to the landing page">
            <ArgosMark variant="stacked" size={112} />
          </Link>
          <div className="argos-rise" style={{ animationDelay: "60ms" }}>
            <h1 className="argos-display argos-signin-title">Sign in</h1>
            <p className="argos-signin-lede">For family and clinicians with an account. A second step follows.</p>
          </div>

          <form className="argos-signin-form" onSubmit={submit} noValidate>
            <div className="argos-rise argos-field" style={{ animationDelay: "120ms" }}>
              <Label htmlFor="signin-email">Email</Label>
              <Input
                id="signin-email"
                type="email"
                inputMode="email"
                autoComplete="email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
              />
            </div>
            <div className="argos-rise argos-field" style={{ animationDelay: "180ms" }}>
              <Label htmlFor="signin-password">Password</Label>
              <div className="argos-password">
                <Input
                  id="signin-password"
                  type={showPassword ? "text" : "password"}
                  autoComplete="current-password"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                />
                <Button
                  type="button"
                  variant="secondary"
                  size="icon"
                  aria-label={showPassword ? "Hide password" : "Show password"}
                  aria-pressed={showPassword}
                  onClick={() => setShowPassword((v) => !v)}
                >
                  {showPassword ? <EyeOff aria-hidden="true" /> : <Eye aria-hidden="true" />}
                </Button>
              </div>
            </div>
            <div className="argos-rise" style={{ animationDelay: "240ms" }}>
              <Button type="submit" className="w-full" disabled={busy}>
                Sign in
              </Button>
            </div>
            <p className="argos-signin-message" role="status">
              {message}
            </p>
          </form>

          <div className="argos-rise argos-or" style={{ animationDelay: "300ms" }}>
            <span>or look around</span>
          </div>

          <div className="argos-rise argos-demo-buttons" style={{ animationDelay: "360ms" }}>
            <Button variant="secondary" onClick={() => openDemo("family")}>
              Open the demo as family
            </Button>
            <Button variant="secondary" onClick={() => openDemo("clinician")}>
              Open the demo as clinician
            </Button>
          </div>
          <p className="argos-rise argos-signin-note" style={{ animationDelay: "420ms" }}>
            The demo plays a scripted run. The live view opens only for signed-in family.
          </p>
        </div>
      </main>

      <aside className="argos-signin-scene">
        <DitherScene caption="Ithaca, on the horizon." className="argos-signin-figure" />
      </aside>
    </div>
  )
}
