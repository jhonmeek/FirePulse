/// <reference types="vite/client" />

interface ImportMetaEnv {
  /** 'true' (défaut) = mocks locaux ; 'false' = API Django `/api/v1`. */
  readonly VITE_USE_MOCKS?: string
  /** Base URL de l'API (défaut `/api/v1`, relayée par le proxy Vite en dev). */
  readonly VITE_API_BASE?: string
}

interface ImportMeta {
  readonly env: ImportMetaEnv
}
