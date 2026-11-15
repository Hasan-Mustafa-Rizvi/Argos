import { useNavigate } from "react-router"

import { useAuthClient } from "@/auth/context"
import { SignInLayout } from "@/components/auth/SignInLayout"
import { Button } from "@/components/ui/button"

/** An account that has passed the second factor and is not linked to a dog. Nothing else. */
export function NotLinked() {
  const auth = useAuthClient()
  const navigate = useNavigate()

  async function signOut() {
    await auth.signOut()
    navigate("/sign-in", { replace: true })
  }

  return (
    <SignInLayout>
      <h1 className="argos-display argos-signin-title">Sign in</h1>
      <p className="argos-signin-lede">This account is not linked to a dog yet.</p>
      <Button variant="secondary" onClick={() => void signOut()}>
        Sign out
      </Button>
    </SignInLayout>
  )
}
