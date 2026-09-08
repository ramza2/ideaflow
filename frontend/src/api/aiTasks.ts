import { apiRequest } from "./client";
import type { AiTaskListResponse } from "../types/api";

export async function listAiTasks(workspaceId: string): Promise<AiTaskListResponse> {
  return apiRequest<AiTaskListResponse>(`/workspaces/${workspaceId}/ai-tasks`);
}
