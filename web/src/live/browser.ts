import { createClient, type SupabaseClient } from "@supabase/supabase-js"

import { markClientModule } from "./load"

markClientModule()

let client: SupabaseClient | null = null

/**
 * One client for the tab. The session stays in the browser between visits: a family member
 * remains signed in on their own device. The token is refreshed by the client.
 * Nothing here runs until `loadBrowserClient` imports this module.
 */
export function browserClient(url: string, key: string): SupabaseClient {
  if (!client) {
    client = createClient(url, key, {
      auth: {
        persistSession: true,
        autoRefreshToken: true,
        detectSessionInUrl: false,
      },
    })
  }
  return client
}
