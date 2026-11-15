import * as React from "react"

import { ArgosMark } from "./ArgosMark"
import { PAPER, STATE_INK } from "./ink"
import {
  FINAL_SCALE,
  LOGO_SCALE,
  reducedMotion,
  REVEAL_SPEED,
  SAFETY_MS,
  STILL_MS,
  supportsWebGL2,
  TILE_SIZE,
  TUNING,
} from "./reveal"

const GlassMark = React.lazy(() => import("./GlassMark"))

export interface LogoRevealProps {
  /** Called once, when the reveal ends or is skipped. */
  onDone: () => void
}

/**
 * The Argos mark revealed through a drop of glass, once, between sign-in and the dashboard.
 * Any key or tap skips it. Under reduced motion or without WebGL2 the mark shows still, briefly.
 */
export function LogoReveal({ onDone }: LogoRevealProps) {
  const [mode] = React.useState<"glass" | "still">(() => (reducedMotion() || !supportsWebGL2() ? "still" : "glass"))
  const doneRef = React.useRef(onDone)
  const finished = React.useRef(false)

  React.useLayoutEffect(() => {
    doneRef.current = onDone
  })

  const finish = React.useCallback(() => {
    if (finished.current) return
    finished.current = true
    doneRef.current()
  }, [])

  React.useEffect(() => {
    const timer = setTimeout(finish, mode === "still" ? STILL_MS : SAFETY_MS)
    window.addEventListener("keydown", finish)
    return () => {
      clearTimeout(timer)
      window.removeEventListener("keydown", finish)
    }
  }, [finish, mode])

  return (
    <div
      className="argos-reveal"
      data-testid="logo-reveal"
      data-mode={mode}
      // The glass replays itself on click. A tap here skips instead, and never reaches the glass.
      onClickCapture={(e) => {
        e.stopPropagation()
        e.preventDefault()
        finish()
      }}
    >
      <p className="sr-only" role="status">
        Opening the dashboard. Press any key to skip.
      </p>
      {mode === "still" ? (
        <ArgosMark variant="bold" label="Argos" size="min(300px, 34vmin)" style={{ color: STATE_INK.calm }} />
      ) : (
        <React.Suspense fallback={null}>
          <GlassMark
            look="light"
            background={PAPER}
            logoColor={STATE_INK.calm}
            loop={false}
            iconPlate={false}
            label="Argos"
            speed={REVEAL_SPEED}
            tileSize={TILE_SIZE}
            logoScale={LOGO_SCALE}
            finalScale={FINAL_SCALE}
            tuning={TUNING}
            onEnd={finish}
            style={{ position: "absolute", inset: 0, cursor: "default" }}
          />
        </React.Suspense>
      )}
    </div>
  )
}
