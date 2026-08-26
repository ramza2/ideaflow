export const API_BASE_URL =
  import.meta.env.VITE_API_BASE_URL?.replace(/\/$/, "") || "/api/v1";

export const CSRF_COOKIE_NAME =
  import.meta.env.VITE_AUTH_CSRF_COOKIE_NAME || "ideaflow_csrf";
