import { apiRequest } from "./client";
import type {
  IdeaCreateRequest,
  IdeaDetail,
  IdeaListParams,
  IdeaListResponse,
  IdeaSharePublic,
  IdeaShareInput,
  IdeaUpdateRequest,
} from "../types/api";

function buildQuery(params: IdeaListParams = {}): string {
  const search = new URLSearchParams();
  if (params.q) search.set("q", params.q);
  if (params.stage_id) search.set("stage_id", params.stage_id);
  if (params.category_id) search.set("category_id", params.category_id);
  if (params.priority) search.set("priority", params.priority);
  if (params.feasibility) search.set("feasibility", params.feasibility);
  if (params.visibility) search.set("visibility", params.visibility);
  if (params.author_id) search.set("author_id", params.author_id);
  if (params.assignee_id) search.set("assignee_id", params.assignee_id);
  if (params.limit != null) search.set("limit", String(params.limit));
  if (params.offset != null) search.set("offset", String(params.offset));
  const qs = search.toString();
  return qs ? `?${qs}` : "";
}

export async function listIdeas(
  workspaceId: string,
  params: IdeaListParams = {},
): Promise<IdeaListResponse> {
  return apiRequest<IdeaListResponse>(
    `/workspaces/${workspaceId}/ideas${buildQuery(params)}`,
  );
}

export async function getIdea(
  workspaceId: string,
  ideaId: string,
): Promise<IdeaDetail> {
  return apiRequest<IdeaDetail>(`/workspaces/${workspaceId}/ideas/${ideaId}`);
}

export async function createIdea(
  workspaceId: string,
  payload: IdeaCreateRequest,
): Promise<IdeaDetail> {
  return apiRequest<IdeaDetail>(`/workspaces/${workspaceId}/ideas`, {
    method: "POST",
    body: payload,
    csrf: true,
  });
}

export async function updateIdea(
  workspaceId: string,
  ideaId: string,
  payload: IdeaUpdateRequest,
): Promise<IdeaDetail> {
  return apiRequest<IdeaDetail>(`/workspaces/${workspaceId}/ideas/${ideaId}`, {
    method: "PATCH",
    body: payload,
    csrf: true,
  });
}

export async function deleteIdea(
  workspaceId: string,
  ideaId: string,
): Promise<void> {
  await apiRequest<void>(`/workspaces/${workspaceId}/ideas/${ideaId}`, {
    method: "DELETE",
    csrf: true,
  });
}

export async function getIdeaShares(
  workspaceId: string,
  ideaId: string,
): Promise<IdeaSharePublic[]> {
  return apiRequest<IdeaSharePublic[]>(
    `/workspaces/${workspaceId}/ideas/${ideaId}/shares`,
  );
}

export async function replaceIdeaShares(
  workspaceId: string,
  ideaId: string,
  shares: IdeaShareInput[],
): Promise<IdeaSharePublic[]> {
  return apiRequest<IdeaSharePublic[]>(
    `/workspaces/${workspaceId}/ideas/${ideaId}/shares`,
    {
      method: "PUT",
      body: { shares },
      csrf: true,
    },
  );
}
