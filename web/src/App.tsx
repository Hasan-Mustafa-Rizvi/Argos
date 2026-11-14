import * as React from "react"
import { Navigate, Route, Routes } from "react-router"

import { AuthProvider } from "@/auth/AuthProvider"
import { RedirectIfSignedIn, RequireSession } from "@/auth/guards"
import type { AuthClient } from "@/auth/types"

const Landing = React.lazy(() => import("@/pages/Landing"))
const SignIn = React.lazy(() => import("@/pages/SignIn"))
const DashboardRoute = React.lazy(() => import("@/pages/Dashboard"))

function Paper() {
  return <div style={{ minHeight: "100dvh", background: "var(--paper)" }} />
}

export function AppRoutes() {
  return (
    <React.Suspense fallback={<Paper />}>
      <Routes>
        <Route path="/" element={<Landing />} />
        <Route
          path="/sign-in"
          element={
            <RedirectIfSignedIn>
              <SignIn />
            </RedirectIfSignedIn>
          }
        />
        <Route
          path="/dashboard"
          element={
            <RequireSession>
              <DashboardRoute />
            </RequireSession>
          }
        />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </React.Suspense>
  )
}

export default function App({ auth }: { auth?: AuthClient }) {
  return (
    <AuthProvider client={auth}>
      <AppRoutes />
    </AuthProvider>
  )
}
