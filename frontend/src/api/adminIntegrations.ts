import { apiRequest } from "./client";
import type {
  AdminIntegrationConfigResponse,
  LlmConnectionTestResult,
  WebSearchConnectionTestResult,
} from "../types/api";

export function getAdminIntegrations(): Promise<AdminIntegrationConfigResponse> {
  return apiRequest<AdminIntegrationConfigResponse>("/admin/integrations");
}

export function testLlmConnection(): Promise<LlmConnectionTestResult> {
  return apiRequest<LlmConnectionTestResult>("/admin/integrations/llm/test", {
    method: "POST",
    csrf: true,
  });
}

export function testWebSearchConnection(query: string): Promise<WebSearchConnectionTestResult> {
  return apiRequest<WebSearchConnectionTestResult>("/admin/integrations/web-search/test", {
    method: "POST",
    body: { query },
    csrf: true,
  });
}
