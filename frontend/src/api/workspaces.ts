import { apiRequest } from "./client";
import type {
  CategoryPublic,
  MemberAddRequest,
  MemberPublic,
  MemberRoleUpdate,
  StagePublic,
  TeamWorkspaceCreate,
  WorkspacePublic,
} from "../types/api";

export async function listWorkspaces(): Promise<WorkspacePublic[]> {
  return apiRequest<WorkspacePublic[]>("/workspaces");
}

export async function getWorkspace(workspaceId: string): Promise<WorkspacePublic> {
  return apiRequest<WorkspacePublic>(`/workspaces/${workspaceId}`);
}

export async function createTeamWorkspace(
  payload: TeamWorkspaceCreate,
): Promise<WorkspacePublic> {
  return apiRequest<WorkspacePublic>("/workspaces", {
    method: "POST",
    body: payload,
    csrf: true,
  });
}

export async function listMembers(workspaceId: string): Promise<MemberPublic[]> {
  return apiRequest<MemberPublic[]>(`/workspaces/${workspaceId}/members`);
}

export async function addMember(
  workspaceId: string,
  payload: MemberAddRequest,
): Promise<MemberPublic> {
  return apiRequest<MemberPublic>(`/workspaces/${workspaceId}/members`, {
    method: "POST",
    body: payload,
    csrf: true,
  });
}

export async function updateMemberRole(
  workspaceId: string,
  userId: string,
  payload: MemberRoleUpdate,
): Promise<MemberPublic> {
  return apiRequest<MemberPublic>(`/workspaces/${workspaceId}/members/${userId}`, {
    method: "PATCH",
    body: payload,
    csrf: true,
  });
}

export async function deactivateMember(
  workspaceId: string,
  userId: string,
): Promise<void> {
  await apiRequest<void>(`/workspaces/${workspaceId}/members/${userId}`, {
    method: "DELETE",
    csrf: true,
  });
}

export async function listStages(workspaceId: string): Promise<StagePublic[]> {
  return apiRequest<StagePublic[]>(`/workspaces/${workspaceId}/stages`);
}

export async function listCategories(workspaceId: string): Promise<CategoryPublic[]> {
  return apiRequest<CategoryPublic[]>(`/workspaces/${workspaceId}/categories`);
}
