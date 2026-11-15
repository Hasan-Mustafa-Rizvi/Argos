import * as React from "react"

import { useSession } from "@/auth/context"
import { isDashboardSession } from "@/auth/types"
import { LogoReveal } from "@/components/argos/LogoReveal"
import { markRevealPlayed, revealPlayed } from "@/components/argos/reveal"
import { DashboardScreen } from "@/components/dashboard/DashboardScreen"
import { DataProvider } from "@/data/DataProvider"

/** /dashboard: the glass reveal once per tab session, then the dashboard on this session's data. */
export default function DashboardRoute() {
  const session = useSession()
  const [revealing, setRevealing] = React.useState(() => !revealPlayed())

  React.useEffect(() => {
    if (revealing) markRevealPlayed()
  }, [revealing])

  if (!isDashboardSession(session)) return null
  if (revealing) return <LogoReveal onDone={() => setRevealing(false)} />
  return (
    <DataProvider session={session}>
      <DashboardScreen />
    </DataProvider>
  )
}
