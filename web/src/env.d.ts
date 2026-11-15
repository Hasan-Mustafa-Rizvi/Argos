/// <reference types="vite/client" />

interface ImportMetaEnv {
  /** "replay" plays the scripted run. "live" reads the backend when the two settings below are set. */
  readonly VITE_DATA_MODE?: string
  /** Project URL. Publishable. Read from the environment, never written here. */
  readonly VITE_SUPABASE_URL?: string
  /** Publishable key. Read from the environment, never written here. */
  readonly VITE_SUPABASE_PUBLISHABLE_KEY?: string
}

interface ImportMeta {
  readonly env: ImportMetaEnv
}
