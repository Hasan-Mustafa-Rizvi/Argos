import boldMarkSvg from "/logo/argos-mark-bold.svg?raw"

import { GlassIconReveal, type GlassIconRevealProps } from "@/components/ui/liquid-glass-logo-reveal"

/** The glass reveal with the bold Argos mark. Loaded on demand, with its markup, by LogoReveal. */
export default function GlassMark(props: Omit<GlassIconRevealProps, "logo">) {
  return <GlassIconReveal logo={boldMarkSvg} {...props} />
}
