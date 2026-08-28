import { apiRequest } from "./client";
import type {
  EligibleReviewerList,
  ReviewCompleteRequest,
  ReviewCreateRequest,
  ReviewInboxCounts,
  ReviewInboxResponse,
  ReviewInboxTab,
  ReviewRequest,
} from "../types/api";

export async function listEligibleReviewers(
  workspaceId: string,
  ideaId: string,
): Promise<EligibleReviewerList> {
  return apiRequest<EligibleReviewerList>(
    `/workspaces/${workspaceId}/ideas/${ideaId}/eligible-reviewers`,
  );
}

export async function createReviewRequest(
  workspaceId: string,
  ideaId: string,
  payload: ReviewCreateRequest,
): Promise<ReviewRequest> {
  return apiRequest<ReviewRequest>(`/workspaces/${workspaceId}/ideas/${ideaId}/reviews`, {
    method: "POST",
    body: payload,
    csrf: true,
  });
}

export async function listIdeaReviews(
  workspaceId: string,
  ideaId: string,
): Promise<ReviewRequest[]> {
  return apiRequest<ReviewRequest[]>(`/workspaces/${workspaceId}/ideas/${ideaId}/reviews`);
}

export async function completeReview(
  workspaceId: string,
  reviewId: string,
  payload: ReviewCompleteRequest,
): Promise<ReviewRequest> {
  return apiRequest<ReviewRequest>(`/workspaces/${workspaceId}/reviews/${reviewId}/complete`, {
    method: "POST",
    body: payload,
    csrf: true,
  });
}

export async function cancelReview(
  workspaceId: string,
  reviewId: string,
): Promise<ReviewRequest> {
  return apiRequest<ReviewRequest>(`/workspaces/${workspaceId}/reviews/${reviewId}/cancel`, {
    method: "POST",
    csrf: true,
  });
}

export async function getReviewInbox(
  workspaceId: string,
  tab: ReviewInboxTab,
  params: { limit?: number; offset?: number } = {},
): Promise<ReviewInboxResponse> {
  const search = new URLSearchParams({ tab });
  if (params.limit != null) search.set("limit", String(params.limit));
  if (params.offset != null) search.set("offset", String(params.offset));
  return apiRequest<ReviewInboxResponse>(
    `/workspaces/${workspaceId}/review-inbox?${search.toString()}`,
  );
}

export async function getReviewInboxCounts(workspaceId: string): Promise<ReviewInboxCounts> {
  return apiRequest<ReviewInboxCounts>(`/workspaces/${workspaceId}/review-inbox/counts`);
}
