import * as React from "react"

import { cn } from "@/lib/utils"

export interface PlateProps extends Omit<React.HTMLAttributes<HTMLElement>, "title"> {
  /** The mono label at the top of the plate. */
  label: string
  /** The page's primary panel sits on a 6 px offset block of ink hatching. */
  primary?: boolean
  tone?: "paper" | "night"
  /** Shown at the right of the label row. */
  aside?: React.ReactNode
  /** Classes for the outer wrapper, which is what a grid places. */
  wrapClassName?: string
}

/** A bordered panel with a wash fill and a mono label. */
export function Plate({ label, primary, tone = "paper", aside, wrapClassName, className, children, ...rest }: PlateProps) {
  const id = React.useId()
  return (
    <div className={cn("argos-plate-wrap", wrapClassName)} data-primary={primary || undefined}>
      {primary && <div className="argos-plate-shadow argos-hatch" aria-hidden="true" />}
      <section className={cn("argos-plate", className)} data-tone={tone} aria-labelledby={id} {...rest}>
        <div className="argos-plate-head">
          <h2 id={id} className="argos-label" style={{ margin: 0 }}>
            {label}
          </h2>
          {aside}
        </div>
        {children}
      </section>
    </div>
  )
}
