import * as React from "react"
import { Eye, EyeOff } from "lucide-react"
import { useNavigate } from "react-router"

import { NotLinked } from "@/auth/NotLinked"
import { useAuthClient, useSession } from "@/auth/context"
import type { Role } from "@/auth/types"
import { SignInLayout } from "@/components/auth/SignInLayout"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"

const NOT_YET = "Accounts are not open yet. They arrive in a later build. To look around now, open the demo below."

function qrSrc(qr: string) {
  if (qr.startsWith("data:")) return qr
  return `data:image/svg+xml;charset=utf-8,${encodeURIComponent(qr)}`
}

function DemoEntry({ onOpen }: { onOpen: (role: Role) => void }) {
  return (
    <>
      <div className="argos-or">
        <span>or look around</span>
      </div>
      <div className="argos-demo-buttons">
        <Button variant="secondary" onClick={() => onOpen("family")}>
          Open the demo as family
        </Button>
        <Button variant="secondary" onClick={() => onOpen("clinician")}>
          Open the demo as clinician
        </Button>
      </div>
      <p className="argos-signin-note">The demo plays a scripted run. The live view opens only for signed-in family.</p>
    </>
  )
}

export default function SignIn() {
  const auth = useAuthClient()
  const session = useSession()
  const navigate = useNavigate()
  const [email, setEmail] = React.useState("")
  const [password, setPassword] = React.useState("")
  const [showPassword, setShowPassword] = React.useState(false)
  const [code, setCode] = React.useState("")
  const [message, setMessage] = React.useState("")
  const [busy, setBusy] = React.useState(false)
  const [enrol, setEnrol] = React.useState<{ qr: string; secret: string } | null>(null)

  React.useEffect(() => {
    document.title = "Sign in · Argos"
  }, [])

  React.useEffect(() => {
    if (session?.kind !== "challenge" || session.step !== "enrol") return
    let gone = false
    void auth.beginEnrolment().then((result) => {
      if (gone) return
      if (result.status === "enrol") setEnrol({ qr: result.qr, secret: result.secret })
      else setMessage(result.message)
    })
    return () => {
      gone = true
    }
  }, [auth, session])

  function openDemo(role: Role) {
    auth.openDemo(role)
    navigate("/dashboard", { replace: true })
  }

  async function submitPassword(e: React.FormEvent) {
    e.preventDefault()
    setBusy(true)
    setMessage("")
    const result = await auth.signInWithPassword(email.trim(), password)
    setBusy(false)
    if (result.status === "signed-in") navigate("/dashboard", { replace: true })
    else if (result.status === "unavailable") setMessage(NOT_YET)
    else if (result.status === "error") setMessage(result.message)
  }

  async function submitCode(e: React.FormEvent) {
    e.preventDefault()
    setBusy(true)
    setMessage("")
    const result = await auth.verifyCode(code.trim())
    setBusy(false)
    if (result.status === "signed-in") navigate("/dashboard", { replace: true })
    else if (result.status === "error") {
      setMessage(result.message)
      setCode("")
    }
  }

  if (session?.kind === "unlinked") return <NotLinked />

  if (session?.kind === "challenge") {
    const enrolling = session.step === "enrol"
    return (
      <SignInLayout>
        <div>
          <h1 className="argos-display argos-signin-title">{enrolling ? "Set up an authenticator" : "Check your authenticator"}</h1>
          <p className="argos-signin-lede">
            {enrolling
              ? "Scan the code with an authenticator app, then enter the six digit code it shows."
              : "Enter the six digit code from your authenticator app."}
          </p>
        </div>
        {enrolling && enrol && (
          <div className="argos-enrol">
            <img className="argos-qr" alt="" src={qrSrc(enrol.qr)} />
            <p className="argos-signin-note">If you cannot scan, type this secret into the app.</p>
            <p className="argos-mono argos-secret">{enrol.secret}</p>
          </div>
        )}
        {enrolling && !enrol && message && (
          <Button
            variant="secondary"
            onClick={() => {
              setMessage("")
              void auth.beginEnrolment().then((result) => {
                if (result.status === "enrol") setEnrol({ qr: result.qr, secret: result.secret })
                else setMessage(result.message)
              })
            }}
          >
            Try again
          </Button>
        )}
        <form className="argos-signin-form" onSubmit={(e) => void submitCode(e)} noValidate>
          <div className="argos-field">
            <Label htmlFor="signin-code">Authenticator code</Label>
            <Input
              id="signin-code"
              type="text"
              inputMode="numeric"
              autoComplete="one-time-code"
              autoCorrect="off"
              spellCheck={false}
              maxLength={6}
              value={code}
              onChange={(e) => setCode(e.target.value.replace(/\D/g, "").slice(0, 6))}
            />
          </div>
          <Button type="submit" className="w-full" disabled={busy || (enrolling && !enrol)}>
            Check code
          </Button>
          {message && (
            <p className="argos-signin-message" role="alert">
              {message}
            </p>
          )}
        </form>
        <DemoEntry onOpen={openDemo} />
      </SignInLayout>
    )
  }

  return (
    <SignInLayout>
      <div>
        <h1 className="argos-display argos-signin-title">Sign in</h1>
        <p className="argos-signin-lede">For family and clinicians with an account. A second step follows.</p>
      </div>
      <form className="argos-signin-form" onSubmit={(e) => void submitPassword(e)} noValidate>
        <div className="argos-field">
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
        <div className="argos-field">
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
        <Button type="submit" className="w-full" disabled={busy}>
          Sign in
        </Button>
        {message && (
          <p className="argos-signin-message" role="alert">
            {message}
          </p>
        )}
      </form>
      <DemoEntry onOpen={openDemo} />
    </SignInLayout>
  )
}
