/** Safe internal path check for returnTo redirects. */
export function isSafeReturnPath(path: string): boolean {
  if (!path.startsWith("/")) return false;
  if (path.startsWith("//")) return false;
  if (path.includes("://")) return false;
  if (path.startsWith("/login")) return false;
  if (path.startsWith("/change-password")) return false;
  return true;
}

export function buildLoginUrl(returnTo?: string | null): string {
  if (returnTo && isSafeReturnPath(returnTo)) {
    return `/login?returnTo=${encodeURIComponent(returnTo)}`;
  }
  return "/login";
}

export const LEGACY_PERSONAL_WORKSPACE_ID = "personal";

export function isLegacyPersonalWorkspaceId(id: string | undefined): boolean {
  return id === LEGACY_PERSONAL_WORKSPACE_ID;
}
