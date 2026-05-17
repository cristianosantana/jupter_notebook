/// <reference types="vite/client" />

interface ImportMetaEnv {
  readonly VITE_ORION_API_BASE: string
}

interface ImportMeta {
  readonly env: ImportMetaEnv
}
