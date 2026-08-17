/// <reference types="vite/client" />

interface ImportMetaEnv {
  readonly VITE_APP_PROFILE?: string;
  readonly VITE_ALLOW_REAL_CALL_DATA?: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}
