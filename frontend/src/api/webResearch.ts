import { apiRequest } from "./client";
import type {
  IdeaEvidenceResponse,
  IdeaResearchRunDetailResponse,
  IdeaResearchRunHistoryResponse,
  WebResearchLatestResponse,
  WebResearchPreviewRequest,
  WebResearchRun,
} from "../types/api";

export async function previewWebResearch(
  workspaceId: string,
  sessionId: string,
  payload: WebResearchPreviewRequest,
): Promise<WebResearchRun> {
  return apiRequest<WebResearchRun>(
    `/workspaces/${workspaceId}/ai-sessions/${sessionId}/research-runs/preview`,
    {
      method: "POST",
      body: payload,
      csrf: true,
    },
  );
}

export async function approveWebResearch(
  workspaceId: string,
  sessionId: string,
  runId: string,
): Promise<WebResearchRun> {
  return apiRequest<WebResearchRun>(
    `/workspaces/${workspaceId}/ai-sessions/${sessionId}/research-runs/${runId}/approve`,
    {
      method: "POST",
      csrf: true,
    },
  );
}

export async function cancelWebResearch(
  workspaceId: string,
  sessionId: string,
  runId: string,
): Promise<WebResearchRun> {
  return apiRequest<WebResearchRun>(
    `/workspaces/${workspaceId}/ai-sessions/${sessionId}/research-runs/${runId}/cancel`,
    {
      method: "POST",
      csrf: true,
    },
  );
}

export async function getWebResearchRun(
  workspaceId: string,
  sessionId: string,
  runId: string,
): Promise<WebResearchRun> {
  return apiRequest<WebResearchRun>(
    `/workspaces/${workspaceId}/ai-sessions/${sessionId}/research-runs/${runId}`,
  );
}

export async function getLatestWebResearchRun(
  workspaceId: string,
  sessionId: string,
): Promise<WebResearchLatestResponse> {
  return apiRequest<WebResearchLatestResponse>(
    `/workspaces/${workspaceId}/ai-sessions/${sessionId}/research-runs/latest`,
  );
}

export async function retryWebResearchRun(
  workspaceId: string,
  sessionId: string,
  runId: string,
): Promise<WebResearchRun> {
  return apiRequest<WebResearchRun>(
    `/workspaces/${workspaceId}/ai-sessions/${sessionId}/research-runs/${runId}/retry`,
    {
      method: "POST",
      csrf: true,
    },
  );
}

export async function getIdeaEvidence(
  workspaceId: string,
  ideaId: string,
): Promise<IdeaEvidenceResponse> {
  return apiRequest<IdeaEvidenceResponse>(
    `/workspaces/${workspaceId}/ideas/${ideaId}/evidence`,
  );
}

/** Latest READY research run for Idea detail F5 / re-entry restore. */
export async function getLatestIdeaResearchRun(
  workspaceId: string,
  ideaId: string,
): Promise<WebResearchLatestResponse> {
  return apiRequest<WebResearchLatestResponse>(
    `/workspaces/${workspaceId}/ideas/${ideaId}/research-runs/latest`,
  );
}

/** READY research history for an Idea (lightweight; no evidence payload). */
export async function listIdeaResearchRuns(
  workspaceId: string,
  ideaId: string,
  opts?: { limit?: number; offset?: number },
): Promise<IdeaResearchRunHistoryResponse> {
  const params = new URLSearchParams();
  if (opts?.limit != null) params.set("limit", String(opts.limit));
  if (opts?.offset != null) params.set("offset", String(opts.offset));
  const qs = params.toString();
  return apiRequest<IdeaResearchRunHistoryResponse>(
    `/workspaces/${workspaceId}/ideas/${ideaId}/research-runs${qs ? `?${qs}` : ""}`,
  );
}

/** One READY research run with summary / queries / per-run evidence. */
export async function getIdeaResearchRun(
  workspaceId: string,
  ideaId: string,
  runId: string,
): Promise<IdeaResearchRunDetailResponse> {
  return apiRequest<IdeaResearchRunDetailResponse>(
    `/workspaces/${workspaceId}/ideas/${ideaId}/research-runs/${runId}`,
  );
}
