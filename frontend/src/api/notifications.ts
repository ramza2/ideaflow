import { apiRequest } from "./client";
import type {
  NotificationItem,
  NotificationListResponse,
  NotificationUnreadCount,
} from "../types/api";

export async function listNotifications(
  workspaceId: string,
  params: { limit?: number; offset?: number; unread_only?: boolean } = {},
): Promise<NotificationListResponse> {
  const search = new URLSearchParams();
  if (params.limit != null) search.set("limit", String(params.limit));
  if (params.offset != null) search.set("offset", String(params.offset));
  if (params.unread_only) search.set("unread_only", "true");
  const qs = search.toString();
  return apiRequest<NotificationListResponse>(
    `/workspaces/${workspaceId}/notifications${qs ? `?${qs}` : ""}`,
  );
}

export async function getNotificationUnreadCount(
  workspaceId: string,
): Promise<NotificationUnreadCount> {
  return apiRequest<NotificationUnreadCount>(
    `/workspaces/${workspaceId}/notifications/unread-count`,
  );
}

export async function markNotificationRead(
  workspaceId: string,
  notificationId: string,
): Promise<NotificationItem> {
  return apiRequest<NotificationItem>(
    `/workspaces/${workspaceId}/notifications/${notificationId}/read`,
    { method: "POST", csrf: true },
  );
}

export async function markAllNotificationsRead(workspaceId: string): Promise<void> {
  await apiRequest<void>(`/workspaces/${workspaceId}/notifications/read-all`, {
    method: "POST",
    csrf: true,
  });
}
