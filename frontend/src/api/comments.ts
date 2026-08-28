import { apiRequest } from "./client";
import type {
  CommentCreateRequest,
  CommentListResponse,
  CommentUpdateRequest,
  EligibleReviewerList,
  IdeaComment,
} from "../types/api";

export async function listMentionCandidates(
  workspaceId: string,
  ideaId: string,
): Promise<EligibleReviewerList> {
  return apiRequest<EligibleReviewerList>(
    `/workspaces/${workspaceId}/ideas/${ideaId}/mention-candidates`,
  );
}

export async function listComments(
  workspaceId: string,
  ideaId: string,
  params: { limit?: number; offset?: number } = {},
): Promise<CommentListResponse> {
  const search = new URLSearchParams();
  if (params.limit != null) search.set("limit", String(params.limit));
  if (params.offset != null) search.set("offset", String(params.offset));
  const qs = search.toString();
  return apiRequest<CommentListResponse>(
    `/workspaces/${workspaceId}/ideas/${ideaId}/comments${qs ? `?${qs}` : ""}`,
  );
}

export async function createComment(
  workspaceId: string,
  ideaId: string,
  payload: CommentCreateRequest,
): Promise<IdeaComment> {
  return apiRequest<IdeaComment>(`/workspaces/${workspaceId}/ideas/${ideaId}/comments`, {
    method: "POST",
    body: payload,
    csrf: true,
  });
}

export async function updateComment(
  workspaceId: string,
  ideaId: string,
  commentId: string,
  payload: CommentUpdateRequest,
): Promise<IdeaComment> {
  return apiRequest<IdeaComment>(
    `/workspaces/${workspaceId}/ideas/${ideaId}/comments/${commentId}`,
    {
      method: "PATCH",
      body: payload,
      csrf: true,
    },
  );
}

export async function deleteComment(
  workspaceId: string,
  ideaId: string,
  commentId: string,
): Promise<void> {
  await apiRequest<void>(
    `/workspaces/${workspaceId}/ideas/${ideaId}/comments/${commentId}`,
    {
      method: "DELETE",
      csrf: true,
    },
  );
}
