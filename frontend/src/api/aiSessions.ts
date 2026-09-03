import { apiRequest } from "./client";
import type {
  AiClarificationSubmitRequest,
  AiRefineApplyRequest,
  AiRefineApplyResponse,
  AiRefineSessionCreateRequest,
  AiSession,
  AiSessionConfirmRequest,
  AiSessionConfirmResponse,
  AiSessionCreateRequest,
  AiSessionRegenerateResponse,
  AiSessionReviewDraftSaveRequest,
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

export async function createIdeaRefineSession(
  workspaceId: string,
  ideaId: string,
  payload: AiRefineSessionCreateRequest,
): Promise<AiSession> {
  return apiRequest<AiSession>(
    `/workspaces/${workspaceId}/ideas/${ideaId}/ai-refine-sessions`,
    {
      method: "POST",
      body: payload,
      csrf: true,
    },
  );
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

export async function applyAiRefinement(
  workspaceId: string,
  sessionId: string,
  payload: AiRefineApplyRequest,
): Promise<AiRefineApplyResponse> {
  return apiRequest<AiRefineApplyResponse>(
    `/workspaces/${workspaceId}/ai-sessions/${sessionId}/apply-refinement`,
    {
      method: "POST",
      body: payload,
      csrf: true,
    },
  );
}

export async function saveAiReviewDraft(
  workspaceId: string,
  sessionId: string,
  payload: AiSessionReviewDraftSaveRequest,
): Promise<AiSession> {
  return apiRequest<AiSession>(
    `/workspaces/${workspaceId}/ai-sessions/${sessionId}/review-draft`,
    {
      method: "PUT",
      body: payload,
      csrf: true,
    },
  );
}

export async function regenerateAiSession(
  workspaceId: string,
  sessionId: string,
): Promise<AiSessionRegenerateResponse> {
  return apiRequest<AiSessionRegenerateResponse>(
    `/workspaces/${workspaceId}/ai-sessions/${sessionId}/regenerate`,
    {
      method: "POST",
      csrf: true,
    },
  );
}
