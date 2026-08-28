import { apiRequest } from "./client";
import type {
  AiClarificationSubmitRequest,
  AiSession,
  AiSessionConfirmRequest,
  AiSessionConfirmResponse,
  AiSessionCreateRequest,
} from "../types/api";

export async function createAiSession(
  workspaceId: string,
  payload: AiSessionCreateRequest,
): Promise<AiSession> {
  return apiRequest<AiSession>(`/workspaces/${workspaceId}/ai-sessions`, {
    method: "POST",
    body: payload,
    csrf: true,
  });
}

export async function getAiSession(
  workspaceId: string,
  sessionId: string,
): Promise<AiSession> {
  return apiRequest<AiSession>(
    `/workspaces/${workspaceId}/ai-sessions/${sessionId}`,
  );
}

export async function submitAiClarifications(
  workspaceId: string,
  sessionId: string,
  payload: AiClarificationSubmitRequest,
): Promise<AiSession> {
  return apiRequest<AiSession>(
    `/workspaces/${workspaceId}/ai-sessions/${sessionId}/clarifications`,
    {
      method: "POST",
      body: payload,
      csrf: true,
    },
  );
}

export async function retryAiSession(
  workspaceId: string,
  sessionId: string,
): Promise<AiSession> {
  return apiRequest<AiSession>(
    `/workspaces/${workspaceId}/ai-sessions/${sessionId}/retry`,
    {
      method: "POST",
      csrf: true,
    },
  );
}

export async function confirmAiSession(
  workspaceId: string,
  sessionId: string,
  payload: AiSessionConfirmRequest,
): Promise<AiSessionConfirmResponse> {
  return apiRequest<AiSessionConfirmResponse>(
    `/workspaces/${workspaceId}/ai-sessions/${sessionId}/confirm`,
    {
      method: "POST",
      body: payload,
      csrf: true,
    },
  );
}
