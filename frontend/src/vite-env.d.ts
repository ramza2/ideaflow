/// <reference types="vite/client" />

interface ImportMetaEnv {
  readonly VITE_API_BASE_URL?: string;
  readonly VITE_AUTH_CSRF_COOKIE_NAME?: string;
  readonly VITE_DEV_API_PROXY_TARGET?: string;
  /** Default Idea list search mode when URL omits search_mode. */
  readonly VITE_IDEA_SEARCH_MODE?: "keyword" | "semantic" | "hybrid";
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}
