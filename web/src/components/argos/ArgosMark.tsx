import type * as React from "react"

import { cn } from "@/lib/utils"

const SOURCES = {
  /** The regular emblem, from 64 px up. */
  mark: { src: "/logo/argos-mark.svg", ratio: 1 },
  /** The bold emblem, under 64 px and for the reveal. */
  bold: { src: "/logo/argos-mark-bold.svg", ratio: 1 },
  /** Mark and wordmark side by side, for headers. */
  lockup: { src: "/logo/argos-lockup.svg", ratio: 699 / 200 },
  /** Mark over wordmark, for the landing and sign-in. */
  stacked: { src: "/logo/argos-lockup-stacked.svg", ratio: 841 / 1093 },
} as const

export type ArgosMarkVariant = keyof typeof SOURCES

export interface ArgosMarkProps {
  variant?: ArgosMarkVariant
  /** Width as a CSS length or in pixels. The height follows the drawing. */
  size?: number | string
  /** Accessible name. Without it the mark is decorative. */
  label?: string
  className?: string
  style?: React.CSSProperties
}

/** The Argos mark as drawn, printed in currentColor through a mask of the logo file. */
export function ArgosMark({ variant = "bold", size = 32, label, className, style }: ArgosMarkProps) {
  const { src, ratio } = SOURCES[variant]
  return (
    <span
      role={label ? "img" : undefined}
      aria-label={label}
      aria-hidden={label ? undefined : true}
      className={cn("argos-mark", className)}
      style={{
        ["--argos-mark-src" as string]: `url("${src}")`,
        width: typeof size === "number" ? `${size}px` : size,
        aspectRatio: String(ratio),
        ...style,
      }}
    />
  )
}
