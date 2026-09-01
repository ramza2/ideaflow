import { apiRequest } from "./client";
import type {
  IdeaValidation,
  IdeaValidationCompleteRequest,
  IdeaValidationCreateRequest,
  IdeaValidationListResponse,
  IdeaValidationStartResponse,
  IdeaValidationUpdateRequest,
} from "../types/api";

function base(workspaceId: string, ideaId: string): string {
  return `/workspaces/${workspaceId}/ideas/${ideaId}/validations`;
}

export async function listValidations(
  workspaceId: string,
  ideaId: string,
): Promise<IdeaValidationListResponse> {
  return apiRequest<IdeaValidationListResponse>(base(workspaceId, ideaId));
}

export async function getValidation(
  workspaceId: string,
  ideaId: string,
  validationId: string,
): Promise<IdeaValidation> {
  return apiRequest<IdeaValidation>(`${base(workspaceId, ideaId)}/${validationId}`);
}

export async function createValidation(
  workspaceId: string,
  ideaId: string,
  payload: IdeaValidationCreateRequest,
): Promise<IdeaValidation> {
  return apiRequest<IdeaValidation>(base(workspaceId, ideaId), {
    method: "POST",
    body: payload,
    csrf: true,
  });
}

export async function updateValidation(
  workspaceId: string,
  ideaId: string,
  validationId: string,
  payload: IdeaValidationUpdateRequest,
): Promise<IdeaValidation> {
  return apiRequest<IdeaValidation>(`${base(workspaceId, ideaId)}/${validationId}`, {
    method: "PATCH",
    body: payload,
    csrf: true,
  });
}

export async function markValidationReady(
  workspaceId: string,
  ideaId: string,
  validationId: string,
): Promise<IdeaValidation> {
  return apiRequest<IdeaValidation>(`${base(workspaceId, ideaId)}/${validationId}/ready`, {
    method: "POST",
    csrf: true,
  });
}

export async function startValidation(
  workspaceId: string,
  ideaId: string,
  validationId: string,
): Promise<IdeaValidationStartResponse> {
  return apiRequest<IdeaValidationStartResponse>(
    `${base(workspaceId, ideaId)}/${validationId}/start`,
    { method: "POST", csrf: true },
  );
}

export async function completeValidation(
  workspaceId: string,
  ideaId: string,
  validationId: string,
  payload: IdeaValidationCompleteRequest,
): Promise<IdeaValidation> {
  return apiRequest<IdeaValidation>(
    `${base(workspaceId, ideaId)}/${validationId}/complete`,
    { method: "POST", body: payload, csrf: true },
  );
}

export async function cancelValidation(
  workspaceId: string,
  ideaId: string,
  validationId: string,
): Promise<IdeaValidation> {
  return apiRequest<IdeaValidation>(
    `${base(workspaceId, ideaId)}/${validationId}/cancel`,
    { method: "POST", csrf: true },
  );
}
