import { apiRequest } from "./client";
import type {
  AdminIntegrationConfigResponse,
  EmbeddingConnectionTestResult,
  EmbeddingIntegrationUpdateRequest,
  IntegrationAuditKey,
  IntegrationConfigAuditListResponse,
  LlmConnectionTestResult,
  LlmIntegrationUpdateRequest,
  RuntimeResetRequest,
  WebSearchConnectionTestResult,
  WebSearchIntegrationUpdateRequest,
} from "../types/api";

export function getAdminIntegrations(): Promise<AdminIntegrationConfigResponse> {
  return apiRequest<AdminIntegrationConfigResponse>("/admin/integrations");
}

export function patchLlmIntegration(
  body: LlmIntegrationUpdateRequest,
): Promise<AdminIntegrationConfigResponse> {
  return apiRequest<AdminIntegrationConfigResponse>("/admin/integrations/llm", {
    method: "PATCH",
    body,
    csrf: true,
  });
}

export function patchWebSearchIntegration(
  body: WebSearchIntegrationUpdateRequest,
): Promise<AdminIntegrationConfigResponse> {
  return apiRequest<AdminIntegrationConfigResponse>("/admin/integrations/web-search", {
    method: "PATCH",
    body,
    csrf: true,
  });
}

export function patchEmbeddingIntegration(
  body: EmbeddingIntegrationUpdateRequest,
): Promise<AdminIntegrationConfigResponse> {
  return apiRequest<AdminIntegrationConfigResponse>("/admin/integrations/embedding", {
    method: "PATCH",
    body,
    csrf: true,
  });
}

export function resetLlmRuntimeConfig(
  body: RuntimeResetRequest,
): Promise<AdminIntegrationConfigResponse> {
  return apiRequest<AdminIntegrationConfigResponse>("/admin/integrations/llm/runtime-config", {
    method: "DELETE",
    body,
    csrf: true,
  });
}

export function resetWebSearchRuntimeConfig(
  body: RuntimeResetRequest,
): Promise<AdminIntegrationConfigResponse> {
  return apiRequest<AdminIntegrationConfigResponse>(
    "/admin/integrations/web-search/runtime-config",
    {
      method: "DELETE",
      body,
      csrf: true,
    },
  );
}

export function resetEmbeddingRuntimeConfig(
  body: RuntimeResetRequest,
): Promise<AdminIntegrationConfigResponse> {
  return apiRequest<AdminIntegrationConfigResponse>(
    "/admin/integrations/embedding/runtime-config",
    {
      method: "DELETE",
      body,
      csrf: true,
    },
  );
}

export function listIntegrationConfigAudit(params: {
  integration?: IntegrationAuditKey;
  limit?: number;
} = {}): Promise<IntegrationConfigAuditListResponse> {
  const search = new URLSearchParams();
  if (params.integration) search.set("integration", params.integration);
  if (params.limit != null) search.set("limit", String(params.limit));
  const qs = search.toString();
  return apiRequest<IntegrationConfigAuditListResponse>(
    `/admin/integrations/config-audit${qs ? `?${qs}` : ""}`,
  );
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

export function testEmbeddingConnection(): Promise<EmbeddingConnectionTestResult> {
  return apiRequest<EmbeddingConnectionTestResult>("/admin/integrations/embedding/test", {
    method: "POST",
    csrf: true,
  });
}
