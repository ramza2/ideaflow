import { apiRequest } from "./client";
import type {
  CsrfResponse,
  LoginResponse,
  UserPublic,
} from "../types/api";

export async function fetchCsrf(): Promise<CsrfResponse> {
  return apiRequest<CsrfResponse>("/auth/csrf");
}

export async function login(
  email: string,
  password: string,
): Promise<LoginResponse> {
  const csrf = await fetchCsrf();
  return apiRequest<LoginResponse>("/auth/login", {
    method: "POST",
    body: { email, password },
    csrf: true,
    csrfToken: csrf.csrf_token,
    handleUnauthorized: false,
  });
}

export async function fetchMe(): Promise<UserPublic> {
  return apiRequest<UserPublic>("/auth/me", { handleUnauthorized: false });
}

export async function logout(): Promise<void> {
  await apiRequest<void>("/auth/logout", { method: "POST", csrf: true });
}

export async function changePassword(
  currentPassword: string,
  newPassword: string,
): Promise<void> {
  await apiRequest<void>("/auth/password", {
    method: "PATCH",
    body: { current_password: currentPassword, new_password: newPassword },
    csrf: true,
  });
}
