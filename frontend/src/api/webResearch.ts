import { apiRequest } from "./client";
import type {
  IdeaEvidenceResponse,
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
