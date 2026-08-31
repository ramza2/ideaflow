import { apiRequest } from "./client";
import type {
  AdminPasswordResetRequest,
  AdminUserCreateRequest,
  AdminUserListResponse,
  AdminUserPublic,
  AdminUserUpdateRequest,
} from "../types/api";

export interface AdminUserListParams {
  q?: string;
  status?: string;
  system_role?: string;
  limit?: number;
  offset?: number;
}

export function listAdminUsers(params: AdminUserListParams = {}): Promise<AdminUserListResponse> {
  const search = new URLSearchParams();
  if (params.q) search.set("q", params.q);
  if (params.status) search.set("status", params.status);
  if (params.system_role) search.set("system_role", params.system_role);
  if (params.limit != null) search.set("limit", String(params.limit));
  if (params.offset != null) search.set("offset", String(params.offset));
  const qs = search.toString();
  return apiRequest<AdminUserListResponse>(`/admin/users${qs ? `?${qs}` : ""}`);
}

export function createAdminUser(body: AdminUserCreateRequest): Promise<AdminUserPublic> {
  return apiRequest<AdminUserPublic>("/admin/users", { method: "POST", body, csrf: true });
}

export function updateAdminUser(
  userId: string,
  body: AdminUserUpdateRequest,
): Promise<AdminUserPublic> {
  return apiRequest<AdminUserPublic>(`/admin/users/${userId}`, {
    method: "PATCH",
    body,
    csrf: true,
  });
}

export function resetAdminUserPassword(
  userId: string,
  body: AdminPasswordResetRequest,
): Promise<AdminUserPublic> {
  return apiRequest<AdminUserPublic>(`/admin/users/${userId}/reset-password`, {
    method: "POST",
    body,
    csrf: true,
  });
}

export function unlockAdminUserLogin(userId: string): Promise<AdminUserPublic> {
  return apiRequest<AdminUserPublic>(`/admin/users/${userId}/unlock-login`, {
    method: "POST",
    csrf: true,
  });
}
