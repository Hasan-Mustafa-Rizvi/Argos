/// <reference types="vite/client" />

interface ImportMetaEnv {
  /** Where the dashboard reads from. Only "replay" is built. */
  readonly VITE_DATA_MODE?: string
}

interface ImportMeta {
  readonly env: ImportMetaEnv
}
