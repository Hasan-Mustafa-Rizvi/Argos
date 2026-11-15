import type * as React from "react"

import { cn } from "@/lib/utils"

/** A full pill with a 1 px ink border and a mono label. */
export function Chip({ className, ...props }: React.HTMLAttributes<HTMLSpanElement>) {
  return <span className={cn("argos-chip", className)} {...props} />
}
