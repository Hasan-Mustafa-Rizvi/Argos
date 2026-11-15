import type { Gateway } from "./ports"

let pending: Promise<Gateway> | null = null

/** One gateway for the tab, created the first time a live session needs it. */
export function sharedGateway(): Promise<Gateway> {
  if (!pending) {
    pending = import("./load").then(async ({ loadBrowserClient }) => {
      const client = await loadBrowserClient()
      const { createGateway } = await import("./gateway")
      return createGateway(client)
    })
  }
  return pending
}
