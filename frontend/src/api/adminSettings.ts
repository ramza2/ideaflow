import { apiRequest } from "./client";
import type { SystemSettingsResponse, SystemSettingsUpdateRequest } from "../types/api";

export function getSystemSettings(): Promise<SystemSettingsResponse> {
  return apiRequest<SystemSettingsResponse>("/admin/system-settings");
}

export function patchSystemSettings(
  body: SystemSettingsUpdateRequest,
): Promise<SystemSettingsResponse> {
  return apiRequest<SystemSettingsResponse>("/admin/system-settings", {
    method: "PATCH",
    body,
    csrf: true,
  });
}
