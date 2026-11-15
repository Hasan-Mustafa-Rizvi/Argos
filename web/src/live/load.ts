/**
 * The module that constructs the backend client. It is loaded with a dynamic import, and only
 * after the settings say the site is live. Importing this file does not load it.
 */

let loaded = false

export function markClientModule(): void {
  loaded = true
}

export function clientModuleLoaded(): boolean {
  return loaded
}

export async function loadBrowserClient() {
  const { liveSettings } = await import("./settings")
  const settings = liveSettings()
  if (!settings) throw new Error("Live settings are not set.")
  const { browserClient } = await import("./browser")
  return browserClient(settings.url, settings.key)
}
