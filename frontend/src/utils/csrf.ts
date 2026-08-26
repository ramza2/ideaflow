import { CSRF_COOKIE_NAME } from "../api/config";

/** Read CSRF token from the JS-readable auth cookie. */
export function getCsrfTokenFromCookie(): string | null {
  if (typeof document === "undefined") return null;
  const prefix = `${encodeURIComponent(CSRF_COOKIE_NAME)}=`;
  const cookies = document.cookie.split("; ");
  for (const cookie of cookies) {
    if (cookie.startsWith(prefix)) {
      return decodeURIComponent(cookie.slice(prefix.length));
    }
  }
  return null;
}
