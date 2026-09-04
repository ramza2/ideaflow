import { useEffect, useState } from "react";
import { clsx } from "clsx";
import {
  Wifi,
  RefreshCw,
  Globe,
  Cpu,
  Database,
  Pencil,
  RotateCcw,
} from "lucide-react";
import { AdminShell } from "../../components/admin/AdminShell";
import { Button } from "../../components/common/Button";
import { ConfirmDialog } from "../../components/common/ConfirmDialog";
import { InlineAlert } from "../../components/common/EmptyState";
import { Switch } from "../../components/common/Input";
import { toast } from "../../components/common/Toast";
import {
  getAdminIntegrations,
  listIntegrationConfigAudit,
  patchEmbeddingIntegration,
  patchLlmIntegration,
  patchWebSearchIntegration,
  resetEmbeddingRuntimeConfig,
  resetLlmRuntimeConfig,
  resetWebSearchRuntimeConfig,
  testEmbeddingConnection,
  testLlmConnection,
  testWebSearchConnection,
} from "../../api/adminIntegrations";
import { apiErrorMessage } from "../../api/client";
import type {
  AdminIntegrationConfigResponse,
  EmbeddingConnectionTestResult,
  EmbeddingIntegrationConfig,
  EmbeddingIntegrationUpdateRequest,
  IntegrationApiKeyAction,
  IntegrationAuditKey,
  IntegrationConfigAuditItem,
  IntegrationRuntimeMeta,
  LlmConnectionTestResult,
  LlmIntegrationConfig,
  LlmIntegrationUpdateRequest,
  WebSearchConnectionTestResult,
  WebSearchIntegrationConfig,
  WebSearchIntegrationUpdateRequest,
} from "../../types/api";

type AdminTab = "llm" | "websearch" | "embedding";

type ThinkingUi = "default" | "on" | "off";

type ApiKeyDraft = {
  action: IntegrationApiKeyAction;
  value: string;
};

type LlmDraft = {
  api_url: string;
  model_name: string;
  chat_completions_path: string;
  timeout_seconds: string;
  connect_timeout_seconds: string;
  temperature: string;
  max_tokens: string;
  thinking: ThinkingUi;
  apiKey: ApiKeyDraft;
};

type WebSearchDraft = {
  provider: string;
  api_url: string;
  timeout_seconds: string;
  connect_timeout_seconds: string;
  max_queries: string;
  max_results_per_query: string;
  max_total_results: string;
  apiKey: ApiKeyDraft;
};

type EmbeddingDraft = {
  enabled: boolean;
  provider: string;
  api_url: string;
  model_name: string;
  embedding_path: string;
  timeout_seconds: string;
  connect_timeout_seconds: string;
  max_input_chars: string;
  apiKey: ApiKeyDraft;
};

const AUDIT_LIMIT = 8;

const TAB_AUDIT_KEY: Record<AdminTab, IntegrationAuditKey> = {
  llm: "LLM",
  websearch: "WEB_SEARCH",
  embedding: "EMBEDDING",
};

const inputClass =
  "h-9 w-full rounded-lg border border-[rgba(0,0,0,0.1)] bg-white px-3 text-sm text-[#111118] focus:outline-none focus:ring-2 focus:ring-[#4f46e5]/20 focus:border-[#4f46e5]";
const readOnlyClass =
  "h-9 w-full rounded-lg border border-[rgba(0,0,0,0.1)] bg-[#f8f8fb] px-3 text-sm text-[#6b6b80]";
const selectClass = inputClass;

function thinkingFromConfig(value: boolean | null): ThinkingUi {
  if (value === true) return "on";
  if (value === false) return "off";
  return "default";
}

function thinkingToValue(ui: ThinkingUi): boolean | null {
  if (ui === "on") return true;
  if (ui === "off") return false;
  return null;
}

function thinkingLabel(value: boolean | null): string {
  if (value === true) return "켬";
  if (value === false) return "끔";
  return "기본값 사용";
}

function apiKeySourceLabel(source: string): string {
  if (source === "RUNTIME") return "Runtime";
  if (source === "ENVIRONMENT") return "환경변수";
  return "";
}

function apiKeyStatusText(meta: IntegrationRuntimeMeta): string {
  if (!meta.api_key_configured) return "현재: 미설정";
  const src = apiKeySourceLabel(meta.api_key_source);
  return src ? `현재: 설정됨 · ${src}` : "현재: 설정됨";
}

function auditActionLabel(action: string): string {
  switch (action) {
    case "CREATED":
      return "생성";
    case "UPDATED":
      return "수정";
    case "SECRET_REPLACED":
      return "API Key 교체";
    case "SECRET_CLEARED":
      return "API Key 제거";
    case "SECRET_INHERIT_ENV":
      return "API Key 환경변수 사용";
    case "RESET_TO_ENV":
      return "환경값으로 되돌림";
    default:
      return action;
  }
}

function formatAuditTime(iso: string): string {
  try {
    return new Date(iso).toLocaleString("ko-KR");
  } catch {
    return iso;
  }
}

function parseNumber(raw: string, label: string): number {
  const n = Number(raw);
  if (!Number.isFinite(n)) {
    throw new Error(`${label} 값이 올바르지 않습니다.`);
  }
  return n;
}

function parseIntStrict(raw: string, label: string): number {
  const n = parseNumber(raw, label);
  if (!Number.isInteger(n)) {
    throw new Error(`${label}은(는) 정수여야 합니다.`);
  }
  return n;
}

function ConfigBadge({ configured }: { configured: boolean }) {
  return (
    <span
      className={clsx(
        "text-xs px-2 py-0.5 rounded-md font-medium",
        configured ? "bg-[#dcfce7] text-[#16a34a]" : "bg-[#f3f4f6] text-[#6b6b80]",
      )}
    >
      {configured ? "설정됨" : "미설정"}
    </span>
  );
}

function SourceBadge({ source }: { source: string }) {
  const isRuntime = source === "RUNTIME";
  return (
    <span
      className={clsx(
        "text-xs px-2 py-0.5 rounded-md font-medium",
        isRuntime ? "bg-[#dbeafe] text-[#1d4ed8]" : "bg-[#ede9fe] text-[#4f46e5]",
      )}
    >
      {isRuntime ? "Runtime 설정" : "환경변수 사용 중"}
    </span>
  );
}

function EnvManageBadge() {
  return (
    <span className="text-xs px-2 py-0.5 rounded-md font-medium bg-[#ede9fe] text-[#4f46e5]">
      환경변수 관리
    </span>
  );
}

function FieldLabel({ children }: { children: React.ReactNode }) {
  return <label className="text-sm font-medium text-[#111118]">{children}</label>;
}

function ReadOnlyField({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex flex-col gap-1.5">
      <FieldLabel>{label}</FieldLabel>
      <input value={value} readOnly className={readOnlyClass} />
    </div>
  );
}

function EditableField({
  label,
  value,
  onChange,
  editing,
  type = "text",
  placeholder,
}: {
  label: string;
  value: string;
  onChange: (v: string) => void;
  editing: boolean;
  type?: string;
  placeholder?: string;
}) {
  return (
    <div className="flex flex-col gap-1.5">
      <FieldLabel>{label}</FieldLabel>
      <input
        type={type}
        value={value}
        readOnly={!editing}
        onChange={(e) => onChange(e.target.value)}
        placeholder={placeholder}
        className={editing ? inputClass : readOnlyClass}
      />
    </div>
  );
}

function ApiKeyEditor({
  meta,
  editing,
  draft,
  onChange,
}: {
  meta: IntegrationRuntimeMeta;
  editing: boolean;
  draft: ApiKeyDraft;
  onChange: (next: ApiKeyDraft) => void;
}) {
  return (
    <div className="flex flex-col gap-1.5 sm:col-span-2">
      <FieldLabel>API Key</FieldLabel>
      {!editing ? (
        <div className="flex items-center gap-2">
          <ConfigBadge configured={meta.api_key_configured} />
          <span className="text-xs text-[#6b6b80]">{apiKeyStatusText(meta)}</span>
        </div>
      ) : (
        <div className="space-y-2">
          <p className="text-xs text-[#6b6b80]">{apiKeyStatusText(meta)}</p>
          <select
            value={draft.action}
            onChange={(e) =>
              onChange({
                action: e.target.value as IntegrationApiKeyAction,
                value: e.target.value === "REPLACE" ? draft.value : "",
              })
            }
            className={selectClass}
          >
            <option value="KEEP">현재 값 유지</option>
            <option value="REPLACE" disabled={!meta.secret_storage_ready}>
              새 값으로 교체
            </option>
            <option value="CLEAR">제거</option>
            <option value="INHERIT_ENV">환경변수 값 사용</option>
          </select>
          {!meta.secret_storage_ready && (
            <InlineAlert type="warning" title="비밀키 저장 불가">
              Runtime에 새 API Key를 저장하려면 서버의 INTEGRATION_SECRET_ENCRYPTION_KEY가
              필요합니다. 교체 옵션이 비활성화됩니다.
            </InlineAlert>
          )}
          {draft.action === "REPLACE" && (
            <input
              type="password"
              autoComplete="new-password"
              value={draft.value}
              onChange={(e) => onChange({ ...draft, value: e.target.value })}
              placeholder="새 API Key 입력"
              className={inputClass}
            />
          )}
        </div>
      )}
    </div>
  );
}

function RecentAuditPanel({
  items,
  loading,
}: {
  items: IntegrationConfigAuditItem[];
  loading: boolean;
}) {
  return (
    <div className="rounded-xl border border-[rgba(0,0,0,0.08)] p-4 bg-[#f8f8fb]">
      <p className="text-sm font-semibold text-[#111118] mb-3">최근 설정 변경</p>
      {loading ? (
        <p className="text-xs text-[#9ca3af]">불러오는 중...</p>
      ) : items.length === 0 ? (
        <p className="text-xs text-[#9ca3af]">최근 변경 이력이 없습니다.</p>
      ) : (
        <ul className="space-y-2">
          {items.map((item) => (
            <li
              key={item.id}
              className="bg-white rounded-lg border border-[rgba(0,0,0,0.07)] px-3 py-2"
            >
              <div className="flex flex-wrap items-center gap-x-2 gap-y-0.5 text-xs">
                <span className="font-medium text-[#111118]">
                  {auditActionLabel(item.action)}
                </span>
                <span className="text-[#9ca3af]">rev {item.revision}</span>
                <span className="text-[#6b6b80]">{formatAuditTime(item.created_at)}</span>
                <span className="text-[#6b6b80]">
                  {item.actor?.name ? item.actor.name : "시스템"}
                </span>
              </div>
              {item.changed_fields.length > 0 && (
                <p className="text-[11px] text-[#9ca3af] mt-1 truncate">
                  {item.changed_fields.join(", ")}
                </p>
              )}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

function llmDraftFromConfig(c: LlmIntegrationConfig): LlmDraft {
  return {
    api_url: c.api_url ?? "",
    model_name: c.model_name ?? "",
    chat_completions_path: c.chat_completions_path ?? "",
    timeout_seconds: String(c.timeout_seconds),
    connect_timeout_seconds: String(c.connect_timeout_seconds),
    temperature: String(c.temperature),
    max_tokens: String(c.max_tokens),
    thinking: thinkingFromConfig(c.enable_thinking),
    apiKey: { action: "KEEP", value: "" },
  };
}

function webSearchDraftFromConfig(c: WebSearchIntegrationConfig): WebSearchDraft {
  return {
    provider: c.provider || "http_json",
    api_url: c.api_url ?? "",
    timeout_seconds: String(c.timeout_seconds),
    connect_timeout_seconds: String(c.connect_timeout_seconds),
    max_queries: String(c.max_queries),
    max_results_per_query: String(c.max_results_per_query),
    max_total_results: String(c.max_total_results),
    apiKey: { action: "KEEP", value: "" },
  };
}

function embeddingDraftFromConfig(c: EmbeddingIntegrationConfig): EmbeddingDraft {
  return {
    enabled: c.enabled,
    provider: c.provider ?? "",
    api_url: c.api_url ?? "",
    model_name: c.model_name ?? "",
    embedding_path: c.embedding_path ?? "",
    timeout_seconds: String(c.timeout_seconds),
    connect_timeout_seconds: String(c.connect_timeout_seconds),
    max_input_chars: String(c.max_input_chars),
    apiKey: { action: "KEEP", value: "" },
  };
}

function isLlmDirty(draft: LlmDraft, c: LlmIntegrationConfig): boolean {
  const base = llmDraftFromConfig(c);
  return (
    draft.api_url !== base.api_url ||
    draft.model_name !== base.model_name ||
    draft.chat_completions_path !== base.chat_completions_path ||
    draft.timeout_seconds !== base.timeout_seconds ||
    draft.connect_timeout_seconds !== base.connect_timeout_seconds ||
    draft.temperature !== base.temperature ||
    draft.max_tokens !== base.max_tokens ||
    draft.thinking !== base.thinking ||
    draft.apiKey.action !== "KEEP"
  );
}

function isWebSearchDirty(draft: WebSearchDraft, c: WebSearchIntegrationConfig): boolean {
  const base = webSearchDraftFromConfig(c);
  return (
    draft.provider !== base.provider ||
    draft.api_url !== base.api_url ||
    draft.timeout_seconds !== base.timeout_seconds ||
    draft.connect_timeout_seconds !== base.connect_timeout_seconds ||
    draft.max_queries !== base.max_queries ||
    draft.max_results_per_query !== base.max_results_per_query ||
    draft.max_total_results !== base.max_total_results ||
    draft.apiKey.action !== "KEEP"
  );
}

function isEmbeddingDirty(draft: EmbeddingDraft, c: EmbeddingIntegrationConfig): boolean {
  const base = embeddingDraftFromConfig(c);
  return (
    draft.enabled !== base.enabled ||
    draft.provider !== base.provider ||
    draft.api_url !== base.api_url ||
    draft.model_name !== base.model_name ||
    draft.embedding_path !== base.embedding_path ||
    draft.timeout_seconds !== base.timeout_seconds ||
    draft.connect_timeout_seconds !== base.connect_timeout_seconds ||
    draft.max_input_chars !== base.max_input_chars ||
    draft.apiKey.action !== "KEEP"
  );
}

function sourceHelpText(source: string): string {
  if (source === "RUNTIME") {
    return "관리자가 저장한 Runtime 설정을 사용 중입니다. 저장한 변경사항은 다음 작업부터 적용됩니다.";
  }
  return "현재 서버 환경변수 값을 사용하고 있습니다. 설정을 편집해 저장하면 Runtime 설정이 우선 적용됩니다.";
}

export function AdminIntegrationsPage() {
  const [tab, setTab] = useState<AdminTab>("llm");
  const [config, setConfig] = useState<AdminIntegrationConfigResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const [editing, setEditing] = useState(false);
  const [saving, setSaving] = useState(false);
  const [resetting, setResetting] = useState(false);
  const [resetConfirmOpen, setResetConfirmOpen] = useState(false);

  const [llmDraft, setLlmDraft] = useState<LlmDraft | null>(null);
  const [wsDraft, setWsDraft] = useState<WebSearchDraft | null>(null);
  const [embDraft, setEmbDraft] = useState<EmbeddingDraft | null>(null);

  const [auditItems, setAuditItems] = useState<IntegrationConfigAuditItem[]>([]);
  const [auditLoading, setAuditLoading] = useState(false);

  const [llmTest, setLlmTest] = useState<LlmConnectionTestResult | null>(null);
  const [llmTesting, setLlmTesting] = useState(false);

  const [wsTestQuery, setWsTestQuery] = useState("Python official documentation");
  const [wsTest, setWsTest] = useState<WebSearchConnectionTestResult | null>(null);
  const [wsTesting, setWsTesting] = useState(false);

  const [embTest, setEmbTest] = useState<EmbeddingConnectionTestResult | null>(null);
  const [embTesting, setEmbTesting] = useState(false);

  const dirty =
    editing &&
    config &&
    ((tab === "llm" && llmDraft && isLlmDirty(llmDraft, config.llm)) ||
      (tab === "websearch" && wsDraft && isWebSearchDirty(wsDraft, config.web_search)) ||
      (tab === "embedding" && embDraft && isEmbeddingDirty(embDraft, config.embedding)));

  async function loadAudit(forTab: AdminTab) {
    setAuditLoading(true);
    try {
      const res = await listIntegrationConfigAudit({
        integration: TAB_AUDIT_KEY[forTab],
        limit: AUDIT_LIMIT,
      });
      setAuditItems(res.items);
    } catch {
      setAuditItems([]);
    } finally {
      setAuditLoading(false);
    }
  }

  async function loadConfig() {
    setLoading(true);
    setError(null);
    try {
      const data = await getAdminIntegrations();
      setConfig(data);
      if (!editing) {
        setLlmDraft(llmDraftFromConfig(data.llm));
        setWsDraft(webSearchDraftFromConfig(data.web_search));
        setEmbDraft(embeddingDraftFromConfig(data.embedding));
      }
    } catch (err) {
      setError(apiErrorMessage(err, "연동 설정을 불러오지 못했습니다."));
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    void loadConfig();
  }, []);

  useEffect(() => {
    void loadAudit(tab);
  }, [tab]);

  useEffect(() => {
    if (!dirty) return;
    const handler = (e: BeforeUnloadEvent) => {
      e.preventDefault();
      e.returnValue = "";
    };
    window.addEventListener("beforeunload", handler);
    return () => window.removeEventListener("beforeunload", handler);
  }, [dirty]);

  function beginEdit() {
    if (!config) return;
    setLlmDraft(llmDraftFromConfig(config.llm));
    setWsDraft(webSearchDraftFromConfig(config.web_search));
    setEmbDraft(embeddingDraftFromConfig(config.embedding));
    setEditing(true);
  }

  function cancelEdit() {
    if (!config) return;
    setLlmDraft(llmDraftFromConfig(config.llm));
    setWsDraft(webSearchDraftFromConfig(config.web_search));
    setEmbDraft(embeddingDraftFromConfig(config.embedding));
    setEditing(false);
  }

  function handleTabChange(next: AdminTab) {
    if (next === tab) return;
    if (dirty) {
      if (!window.confirm("저장하지 않은 변경사항이 있습니다. 탭을 전환하면 편집이 취소됩니다.")) {
        return;
      }
      cancelEdit();
    } else if (editing) {
      cancelEdit();
    }
    setTab(next);
  }

  function applySavedConfig(data: AdminIntegrationConfigResponse) {
    setConfig(data);
    setLlmDraft(llmDraftFromConfig(data.llm));
    setWsDraft(webSearchDraftFromConfig(data.web_search));
    setEmbDraft(embeddingDraftFromConfig(data.embedding));
    setEditing(false);
    void loadAudit(tab);
  }

  async function saveLlm() {
    if (!config || !llmDraft || saving) return;
    if (llmDraft.apiKey.action === "REPLACE" && !llmDraft.apiKey.value.trim()) {
      toast.error("새 API Key를 입력해 주세요.");
      return;
    }
    setSaving(true);
    try {
      const body: LlmIntegrationUpdateRequest = {
        expected_revision: config.llm.runtime_revision,
        api_key_action: llmDraft.apiKey.action,
      };
      if (llmDraft.api_url !== (config.llm.api_url ?? "")) body.api_url = llmDraft.api_url;
      if (llmDraft.model_name !== config.llm.model_name) body.model_name = llmDraft.model_name;
      if (llmDraft.chat_completions_path !== config.llm.chat_completions_path) {
        body.chat_completions_path = llmDraft.chat_completions_path;
      }
      if (Number(llmDraft.timeout_seconds) !== config.llm.timeout_seconds) {
        body.timeout_seconds = parseNumber(llmDraft.timeout_seconds, "Timeout");
      }
      if (Number(llmDraft.connect_timeout_seconds) !== config.llm.connect_timeout_seconds) {
        body.connect_timeout_seconds = parseNumber(
          llmDraft.connect_timeout_seconds,
          "Connect timeout",
        );
      }
      if (Number(llmDraft.temperature) !== config.llm.temperature) {
        body.temperature = parseNumber(llmDraft.temperature, "Temperature");
      }
      if (Number(llmDraft.max_tokens) !== config.llm.max_tokens) {
        body.max_tokens = parseIntStrict(llmDraft.max_tokens, "최대 출력");
      }
      if (llmDraft.thinking !== thinkingFromConfig(config.llm.enable_thinking)) {
        body.enable_thinking = thinkingToValue(llmDraft.thinking);
      }
      if (llmDraft.apiKey.action === "REPLACE") {
        body.api_key = llmDraft.apiKey.value;
      }
      const updated = await patchLlmIntegration(body);
      applySavedConfig(updated);
      toast.success("LLM 설정이 저장되었습니다.");
    } catch (err) {
      toast.error(apiErrorMessage(err, "LLM 설정 저장에 실패했습니다."));
    } finally {
      setSaving(false);
    }
  }

  async function saveWebSearch() {
    if (!config || !wsDraft || saving) return;
    if (wsDraft.apiKey.action === "REPLACE" && !wsDraft.apiKey.value.trim()) {
      toast.error("새 API Key를 입력해 주세요.");
      return;
    }
    setSaving(true);
    try {
      const body: WebSearchIntegrationUpdateRequest = {
        expected_revision: config.web_search.runtime_revision,
        api_key_action: wsDraft.apiKey.action,
      };
      if (wsDraft.provider !== config.web_search.provider) body.provider = wsDraft.provider;
      if (wsDraft.api_url !== (config.web_search.api_url ?? "")) body.api_url = wsDraft.api_url;
      if (Number(wsDraft.timeout_seconds) !== config.web_search.timeout_seconds) {
        body.timeout_seconds = parseNumber(wsDraft.timeout_seconds, "Timeout");
      }
      if (Number(wsDraft.connect_timeout_seconds) !== config.web_search.connect_timeout_seconds) {
        body.connect_timeout_seconds = parseNumber(
          wsDraft.connect_timeout_seconds,
          "Connect timeout",
        );
      }
      if (Number(wsDraft.max_queries) !== config.web_search.max_queries) {
        body.max_queries = parseIntStrict(wsDraft.max_queries, "최대 쿼리 수");
      }
      if (Number(wsDraft.max_results_per_query) !== config.web_search.max_results_per_query) {
        body.max_results_per_query = parseIntStrict(
          wsDraft.max_results_per_query,
          "결과 수",
        );
      }
      if (Number(wsDraft.max_total_results) !== config.web_search.max_total_results) {
        body.max_total_results = parseIntStrict(wsDraft.max_total_results, "총 결과 수");
      }
      if (wsDraft.apiKey.action === "REPLACE") {
        body.api_key = wsDraft.apiKey.value;
      }
      const updated = await patchWebSearchIntegration(body);
      applySavedConfig(updated);
      toast.success("웹 검색 설정이 저장되었습니다.");
    } catch (err) {
      toast.error(apiErrorMessage(err, "웹 검색 설정 저장에 실패했습니다."));
    } finally {
      setSaving(false);
    }
  }

  async function saveEmbedding() {
    if (!config || !embDraft || saving) return;
    if (embDraft.apiKey.action === "REPLACE" && !embDraft.apiKey.value.trim()) {
      toast.error("새 API Key를 입력해 주세요.");
      return;
    }
    const providerChanged = embDraft.provider !== config.embedding.provider;
    const modelChanged = embDraft.model_name !== config.embedding.model_name;
    if (providerChanged || modelChanged) {
      const ok = window.confirm(
        "임베딩 Provider 또는 Model을 변경하면 기존 벡터와 호환되지 않을 수 있습니다. 재인덱스가 필요할 수 있습니다. 계속하시겠습니까?",
      );
      if (!ok) return;
    }
    setSaving(true);
    try {
      const body: EmbeddingIntegrationUpdateRequest = {
        expected_revision: config.embedding.runtime_revision,
        api_key_action: embDraft.apiKey.action,
      };
      if (embDraft.enabled !== config.embedding.enabled) body.enabled = embDraft.enabled;
      if (providerChanged) body.provider = embDraft.provider;
      if (embDraft.api_url !== (config.embedding.api_url ?? "")) body.api_url = embDraft.api_url;
      if (modelChanged) body.model_name = embDraft.model_name;
      if (embDraft.embedding_path !== config.embedding.embedding_path) {
        body.embedding_path = embDraft.embedding_path;
      }
      if (Number(embDraft.timeout_seconds) !== config.embedding.timeout_seconds) {
        body.timeout_seconds = parseNumber(embDraft.timeout_seconds, "Timeout");
      }
      if (Number(embDraft.connect_timeout_seconds) !== config.embedding.connect_timeout_seconds) {
        body.connect_timeout_seconds = parseNumber(
          embDraft.connect_timeout_seconds,
          "Connect timeout",
        );
      }
      if (Number(embDraft.max_input_chars) !== config.embedding.max_input_chars) {
        body.max_input_chars = parseIntStrict(embDraft.max_input_chars, "최대 입력 길이");
      }
      if (embDraft.apiKey.action === "REPLACE") {
        body.api_key = embDraft.apiKey.value;
      }
      const updated = await patchEmbeddingIntegration(body);
      applySavedConfig(updated);
      toast.success("임베딩 설정이 저장되었습니다.");
    } catch (err) {
      toast.error(apiErrorMessage(err, "임베딩 설정 저장에 실패했습니다."));
    } finally {
      setSaving(false);
    }
  }

  async function handleSave() {
    if (saving) return;
    try {
      if (tab === "llm") await saveLlm();
      else if (tab === "websearch") await saveWebSearch();
      else await saveEmbedding();
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "입력값을 확인해 주세요.");
    }
  }

  async function confirmReset() {
    if (!config || resetting) return;
    setResetting(true);
    try {
      let updated: AdminIntegrationConfigResponse;
      if (tab === "llm") {
        updated = await resetLlmRuntimeConfig({
          expected_revision: config.llm.runtime_revision,
        });
      } else if (tab === "websearch") {
        updated = await resetWebSearchRuntimeConfig({
          expected_revision: config.web_search.runtime_revision,
        });
      } else {
        updated = await resetEmbeddingRuntimeConfig({
          expected_revision: config.embedding.runtime_revision,
        });
      }
      applySavedConfig(updated);
      setResetConfirmOpen(false);
      toast.success("환경변수 값으로 되돌렸습니다.");
    } catch (err) {
      toast.error(apiErrorMessage(err, "환경값으로 되돌리기에 실패했습니다."));
    } finally {
      setResetting(false);
    }
  }

  async function runLlmTest() {
    setLlmTesting(true);
    setLlmTest(null);
    try {
      const result = await testLlmConnection();
      setLlmTest(result);
    } catch (err) {
      toast.error(apiErrorMessage(err, "LLM 연결 테스트에 실패했습니다."));
    } finally {
      setLlmTesting(false);
    }
  }

  async function runWsTest() {
    const query = wsTestQuery.trim();
    if (!query) return;
    setWsTesting(true);
    setWsTest(null);
    try {
      const result = await testWebSearchConnection(query);
      setWsTest(result);
    } catch (err) {
      toast.error(apiErrorMessage(err, "웹 검색 테스트에 실패했습니다."));
    } finally {
      setWsTesting(false);
    }
  }

  async function runEmbTest() {
    setEmbTesting(true);
    setEmbTest(null);
    try {
      const result = await testEmbeddingConnection();
      setEmbTest(result);
    } catch (err) {
      toast.error(apiErrorMessage(err, "임베딩 연결 테스트에 실패했습니다."));
    } finally {
      setEmbTesting(false);
    }
  }

  const statusCards = config
    ? [
        {
          label: "LLM",
          value: config.llm.configured ? "구성됨" : "미설정",
          color: config.llm.configured ? "#16a34a" : "#6b6b80",
        },
        {
          label: "웹 검색",
          value: config.web_search.configured ? "구성됨" : "미설정",
          color: config.web_search.configured ? "#16a34a" : "#6b6b80",
        },
        {
          label: "임베딩",
          value: config.embedding.configured ? "구성됨" : "미설정/비활성",
          color: config.embedding.configured ? "#16a34a" : "#6b6b80",
        },
        {
          label: "전역 AI / 웹 검색",
          value: `${config.global_llm_enabled ? "AI 허용" : "AI 차단"} · ${
            config.global_web_search_enabled ? "검색 허용" : "검색 차단"
          }`,
          color:
            config.global_llm_enabled && config.global_web_search_enabled ? "#16a34a" : "#d97706",
        },
      ]
    : [];

  const TABS: { id: AdminTab; label: string; icon: typeof Cpu }[] = [
    { id: "llm", label: "LLM", icon: Cpu },
    { id: "websearch", label: "웹 검색", icon: Globe },
    { id: "embedding", label: "임베딩", icon: Database },
  ];

  const activeMeta: IntegrationRuntimeMeta | null = config
    ? tab === "llm"
      ? config.llm
      : tab === "websearch"
        ? config.web_search
        : config.embedding
    : null;

  function renderActionBar() {
    if (!activeMeta) return null;
    return (
      <div className="flex flex-wrap items-center gap-2 mb-4">
        {!editing ? (
          <>
            <Button
              variant="secondary"
              size="sm"
              icon={<Pencil className="w-3.5 h-3.5" />}
              onClick={beginEdit}
            >
              설정 편집
            </Button>
            <Button
              variant="secondary"
              size="sm"
              icon={<Wifi className="w-3.5 h-3.5" />}
              onClick={() => {
                if (tab === "llm") void runLlmTest();
                else if (tab === "websearch") void runWsTest();
                else void runEmbTest();
              }}
              loading={
                tab === "llm" ? llmTesting : tab === "websearch" ? wsTesting : embTesting
              }
            >
              연결 테스트
            </Button>
            {activeMeta.runtime_override_exists && (
              <Button
                variant="ghost"
                size="sm"
                icon={<RotateCcw className="w-3.5 h-3.5" />}
                onClick={() => setResetConfirmOpen(true)}
              >
                환경값으로 되돌리기
              </Button>
            )}
          </>
        ) : (
          <>
            <Button variant="ghost" size="sm" onClick={cancelEdit} disabled={saving}>
              취소
            </Button>
            <Button
              variant="primary"
              size="sm"
              loading={saving}
              disabled={saving || !dirty}
              onClick={() => void handleSave()}
            >
              저장
            </Button>
          </>
        )}
      </div>
    );
  }

  return (
    <AdminShell title="AI 및 외부 연계">
      {loading ? (
        <div className="px-8 py-12 text-center text-sm text-[#6b6b80]">불러오는 중...</div>
      ) : error ? (
        <div className="px-8 py-6">
          <InlineAlert type="error" title="오류">
            {error}
          </InlineAlert>
        </div>
      ) : (
        <>
          <div className="px-4 sm:px-8 py-5 grid grid-cols-2 sm:grid-cols-4 gap-4">
            {statusCards.map((card) => (
              <div
                key={card.label}
                className="bg-white rounded-xl border border-[rgba(0,0,0,0.07)] p-4"
              >
                <p className="text-xs text-[#6b6b80] mb-1">{card.label}</p>
                <p className="text-sm font-bold" style={{ color: card.color }}>
                  {card.value}
                </p>
              </div>
            ))}
          </div>

          <div className="px-4 sm:px-8">
            <div className="bg-white rounded-t-xl border border-b-0 border-[rgba(0,0,0,0.07)] px-4 pt-2 flex gap-1 overflow-x-auto">
              {TABS.map((t) => (
                <button
                  key={t.id}
                  type="button"
                  onClick={() => handleTabChange(t.id)}
                  className={clsx(
                    "flex items-center gap-1.5 px-4 py-2.5 text-sm font-medium border-b-2 transition-colors",
                    tab === t.id
                      ? "border-[#4f46e5] text-[#4f46e5]"
                      : "border-transparent text-[#6b6b80] hover:text-[#111118]",
                  )}
                >
                  <t.icon className="w-4 h-4" />
                  {t.label}
                </button>
              ))}
            </div>
          </div>

          <div className="px-4 sm:px-8 pb-8">
            <div className="bg-white rounded-b-xl rounded-tr-xl border border-[rgba(0,0,0,0.07)] p-6">
              {tab === "llm" && config && llmDraft && (
                <div className="space-y-6">
                  <div>
                    <div className="flex items-center gap-2 mb-1">
                      <h3 className="text-base font-bold text-[#111118]">LLM 연결 정보</h3>
                      <SourceBadge source={config.llm.configuration_source} />
                    </div>
                    <p className="text-sm text-[#6b6b80] mb-4">
                      {sourceHelpText(config.llm.configuration_source)}
                    </p>
                    {renderActionBar()}
                    <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                      <ReadOnlyField label="Provider" value="openai_compatible" />
                      <EditableField
                        label="API URL"
                        value={llmDraft.api_url}
                        onChange={(v) => setLlmDraft({ ...llmDraft, api_url: v })}
                        editing={editing}
                      />
                      <EditableField
                        label="모델명"
                        value={llmDraft.model_name}
                        onChange={(v) => setLlmDraft({ ...llmDraft, model_name: v })}
                        editing={editing}
                      />
                      <EditableField
                        label="Chat Completions Path"
                        value={llmDraft.chat_completions_path}
                        onChange={(v) =>
                          setLlmDraft({ ...llmDraft, chat_completions_path: v })
                        }
                        editing={editing}
                      />
                      <ApiKeyEditor
                        meta={config.llm}
                        editing={editing}
                        draft={llmDraft.apiKey}
                        onChange={(apiKey) => setLlmDraft({ ...llmDraft, apiKey })}
                      />
                      <EditableField
                        label="Timeout (초)"
                        value={llmDraft.timeout_seconds}
                        onChange={(v) => setLlmDraft({ ...llmDraft, timeout_seconds: v })}
                        editing={editing}
                        type="number"
                      />
                      <EditableField
                        label="Connect Timeout (초)"
                        value={llmDraft.connect_timeout_seconds}
                        onChange={(v) =>
                          setLlmDraft({ ...llmDraft, connect_timeout_seconds: v })
                        }
                        editing={editing}
                        type="number"
                      />
                      <EditableField
                        label="Temperature"
                        value={llmDraft.temperature}
                        onChange={(v) => setLlmDraft({ ...llmDraft, temperature: v })}
                        editing={editing}
                        type="number"
                      />
                      <EditableField
                        label="최대 출력 (tokens)"
                        value={llmDraft.max_tokens}
                        onChange={(v) => setLlmDraft({ ...llmDraft, max_tokens: v })}
                        editing={editing}
                        type="number"
                      />
                      <div className="flex flex-col gap-1.5">
                        <FieldLabel>Thinking</FieldLabel>
                        {editing ? (
                          <select
                            value={llmDraft.thinking}
                            onChange={(e) =>
                              setLlmDraft({
                                ...llmDraft,
                                thinking: e.target.value as ThinkingUi,
                              })
                            }
                            className={selectClass}
                          >
                            <option value="default">기본값 사용</option>
                            <option value="on">켬</option>
                            <option value="off">끔</option>
                          </select>
                        ) : (
                          <input
                            value={thinkingLabel(config.llm.enable_thinking)}
                            readOnly
                            className={readOnlyClass}
                          />
                        )}
                      </div>
                    </div>
                  </div>

                  <div className="rounded-xl border border-[rgba(0,0,0,0.08)] p-4 bg-[#f8f8fb]">
                    <div className="flex items-center justify-between mb-3">
                      <p className="text-sm font-semibold text-[#111118]">연결 테스트</p>
                      <Button
                        variant="secondary"
                        size="sm"
                        loading={llmTesting}
                        icon={!llmTesting ? <Wifi className="w-3.5 h-3.5" /> : undefined}
                        onClick={() => void runLlmTest()}
                      >
                        테스트 실행
                      </Button>
                    </div>
                    {llmTest?.status === "OK" && (
                      <InlineAlert type="success" title="연결 정상">
                        {llmTest.model} · {llmTest.latency_ms}ms
                      </InlineAlert>
                    )}
                    {llmTest?.status === "ERROR" && (
                      <InlineAlert type="error" title="연결 실패">
                        {llmTest.safe_message ?? llmTest.error_code ?? "오류"}
                      </InlineAlert>
                    )}
                    {!llmTest && !llmTesting && (
                      <p className="text-xs text-[#9ca3af]">
                        테스트를 실행하면 연결 상태를 확인합니다.
                      </p>
                    )}
                  </div>

                  <RecentAuditPanel items={auditItems} loading={auditLoading} />
                </div>
              )}

              {tab === "websearch" && config && wsDraft && (
                <div className="space-y-6">
                  <div>
                    <div className="flex items-center gap-2 mb-1">
                      <h3 className="text-base font-bold text-[#111118]">웹 검색 연결 정보</h3>
                      <SourceBadge source={config.web_search.configuration_source} />
                    </div>
                    <p className="text-sm text-[#6b6b80] mb-4">
                      {sourceHelpText(config.web_search.configuration_source)}
                    </p>
                    {renderActionBar()}
                    <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                      <div className="flex flex-col gap-1.5">
                        <FieldLabel>Provider</FieldLabel>
                        {editing ? (
                          <select
                            value={wsDraft.provider}
                            onChange={(e) =>
                              setWsDraft({ ...wsDraft, provider: e.target.value })
                            }
                            className={selectClass}
                          >
                            <option value="http_json">http_json</option>
                            <option value="tavily">tavily</option>
                          </select>
                        ) : (
                          <input
                            value={config.web_search.provider}
                            readOnly
                            className={readOnlyClass}
                          />
                        )}
                      </div>
                      <EditableField
                        label="API URL"
                        value={wsDraft.api_url}
                        onChange={(v) => setWsDraft({ ...wsDraft, api_url: v })}
                        editing={editing}
                        placeholder="미설정"
                      />
                      <ApiKeyEditor
                        meta={config.web_search}
                        editing={editing}
                        draft={wsDraft.apiKey}
                        onChange={(apiKey) => setWsDraft({ ...wsDraft, apiKey })}
                      />
                      <EditableField
                        label="결과 수 (쿼리당)"
                        value={wsDraft.max_results_per_query}
                        onChange={(v) =>
                          setWsDraft({ ...wsDraft, max_results_per_query: v })
                        }
                        editing={editing}
                        type="number"
                      />
                      <EditableField
                        label="최대 쿼리 수"
                        value={wsDraft.max_queries}
                        onChange={(v) => setWsDraft({ ...wsDraft, max_queries: v })}
                        editing={editing}
                        type="number"
                      />
                      <EditableField
                        label="총 결과 수 상한"
                        value={wsDraft.max_total_results}
                        onChange={(v) => setWsDraft({ ...wsDraft, max_total_results: v })}
                        editing={editing}
                        type="number"
                      />
                      <EditableField
                        label="Timeout (초)"
                        value={wsDraft.timeout_seconds}
                        onChange={(v) => setWsDraft({ ...wsDraft, timeout_seconds: v })}
                        editing={editing}
                        type="number"
                      />
                      <EditableField
                        label="Connect Timeout (초)"
                        value={wsDraft.connect_timeout_seconds}
                        onChange={(v) =>
                          setWsDraft({ ...wsDraft, connect_timeout_seconds: v })
                        }
                        editing={editing}
                        type="number"
                      />
                    </div>
                  </div>

                  <div className="rounded-xl border border-[rgba(0,0,0,0.08)] p-4 bg-[#f8f8fb]">
                    <p className="text-sm font-semibold text-[#111118] mb-1">테스트 검색</p>
                    <p className="text-xs text-[#6b6b80] mb-3">
                      입력한 테스트 검색어가 외부 검색 서비스로 전송됩니다. Idea 데이터는
                      전송되지 않습니다.
                    </p>
                    <div className="flex gap-2">
                      <input
                        value={wsTestQuery}
                        onChange={(e) => setWsTestQuery(e.target.value)}
                        placeholder="검색어를 입력하세요"
                        className="flex-1 h-9 rounded-lg border border-[rgba(0,0,0,0.1)] bg-white px-3 text-sm"
                      />
                      <Button
                        variant="secondary"
                        size="sm"
                        loading={wsTesting}
                        onClick={() => void runWsTest()}
                      >
                        검색
                      </Button>
                    </div>
                    {wsTest?.status === "NOT_CONFIGURED" && (
                      <div className="mt-3">
                        <InlineAlert type="warning" title="미설정">
                          {wsTest.safe_message ?? "웹 검색 API URL이 설정되지 않았습니다."}
                        </InlineAlert>
                      </div>
                    )}
                    {wsTest?.status === "OK" && (
                      <div className="mt-3 space-y-2">
                        <InlineAlert type="success" title="검색 성공">
                          {wsTest.result_count ?? 0}건 · {wsTest.latency_ms}ms
                        </InlineAlert>
                        {(wsTest.results ?? []).map((r, i) => (
                          <div
                            key={i}
                            className="bg-white rounded-lg border border-[rgba(0,0,0,0.07)] p-3"
                          >
                            <p className="text-xs font-medium text-[#4f46e5]">{r.title}</p>
                            <p className="text-xs text-[#6b6b80] mt-0.5 truncate">{r.url}</p>
                          </div>
                        ))}
                      </div>
                    )}
                    {wsTest?.status === "ERROR" && (
                      <div className="mt-3">
                        <InlineAlert type="error" title="검색 실패">
                          {wsTest.safe_message ?? wsTest.error_code ?? "오류"}
                        </InlineAlert>
                      </div>
                    )}
                  </div>

                  <RecentAuditPanel items={auditItems} loading={auditLoading} />
                </div>
              )}

              {tab === "embedding" && config && embDraft && (
                <div className="space-y-6">
                  <div>
                    <div className="flex items-center gap-2 mb-1">
                      <h3 className="text-base font-bold text-[#111118]">임베딩 연결 정보</h3>
                      <SourceBadge source={config.embedding.configuration_source} />
                    </div>
                    <p className="text-sm text-[#6b6b80] mb-4">
                      {sourceHelpText(config.embedding.configuration_source)}
                    </p>
                    {renderActionBar()}
                    <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                      <div className="flex flex-col gap-1.5 sm:col-span-2">
                        <FieldLabel>Runtime 임베딩 사용</FieldLabel>
                        {editing ? (
                          <Switch
                            label={embDraft.enabled ? "ON" : "OFF"}
                            checked={embDraft.enabled}
                            onChange={(v) => setEmbDraft({ ...embDraft, enabled: v })}
                          />
                        ) : (
                          <input
                            value={
                              config.embedding.enabled
                                ? config.embedding.configured
                                  ? "활성"
                                  : "활성(미구성)"
                                : "비활성"
                            }
                            readOnly
                            className={readOnlyClass}
                          />
                        )}
                      </div>
                      <EditableField
                        label="Provider"
                        value={embDraft.provider}
                        onChange={(v) => setEmbDraft({ ...embDraft, provider: v })}
                        editing={editing}
                      />
                      <EditableField
                        label="Model"
                        value={embDraft.model_name}
                        onChange={(v) => setEmbDraft({ ...embDraft, model_name: v })}
                        editing={editing}
                      />
                      <ReadOnlyField
                        label="Dimension"
                        value={String(config.embedding.dimension)}
                      />
                      <EditableField
                        label="API URL"
                        value={embDraft.api_url}
                        onChange={(v) => setEmbDraft({ ...embDraft, api_url: v })}
                        editing={editing}
                        placeholder="미설정"
                      />
                      <EditableField
                        label="Embedding Path"
                        value={embDraft.embedding_path}
                        onChange={(v) => setEmbDraft({ ...embDraft, embedding_path: v })}
                        editing={editing}
                      />
                      <ApiKeyEditor
                        meta={config.embedding}
                        editing={editing}
                        draft={embDraft.apiKey}
                        onChange={(apiKey) => setEmbDraft({ ...embDraft, apiKey })}
                      />
                      <div className="flex flex-col gap-1.5">
                        <FieldLabel>Embedding Worker</FieldLabel>
                        <div className="flex items-center gap-2 h-9">
                          <span className="text-sm text-[#6b6b80]">
                            {config.embedding.worker_enabled ? "활성" : "비활성"}
                          </span>
                          <EnvManageBadge />
                        </div>
                      </div>
                      <EditableField
                        label="Timeout (초)"
                        value={embDraft.timeout_seconds}
                        onChange={(v) => setEmbDraft({ ...embDraft, timeout_seconds: v })}
                        editing={editing}
                        type="number"
                      />
                      <EditableField
                        label="Connect Timeout (초)"
                        value={embDraft.connect_timeout_seconds}
                        onChange={(v) =>
                          setEmbDraft({ ...embDraft, connect_timeout_seconds: v })
                        }
                        editing={editing}
                        type="number"
                      />
                      <EditableField
                        label="최대 입력 길이"
                        value={embDraft.max_input_chars}
                        onChange={(v) => setEmbDraft({ ...embDraft, max_input_chars: v })}
                        editing={editing}
                        type="number"
                      />
                    </div>
                  </div>

                  <div className="rounded-xl border border-[rgba(0,0,0,0.08)] p-4 bg-[#f8f8fb]">
                    <p className="text-sm font-semibold text-[#111118] mb-3">DB 상태</p>
                    <div className="grid grid-cols-2 sm:grid-cols-5 gap-3 text-sm">
                      <div>
                        <p className="text-xs text-[#6b6b80]">저장된 embedding</p>
                        <p className="font-semibold text-[#111118]">
                          {config.embedding.stored_embedding_count}
                        </p>
                      </div>
                      <div>
                        <p className="text-xs text-[#6b6b80]">대기</p>
                        <p className="font-semibold text-[#111118]">
                          {config.embedding.job_counts.queued}
                        </p>
                      </div>
                      <div>
                        <p className="text-xs text-[#6b6b80]">처리 중</p>
                        <p className="font-semibold text-[#111118]">
                          {config.embedding.job_counts.running}
                        </p>
                      </div>
                      <div>
                        <p className="text-xs text-[#6b6b80]">성공</p>
                        <p className="font-semibold text-[#111118]">
                          {config.embedding.job_counts.succeeded}
                        </p>
                      </div>
                      <div>
                        <p className="text-xs text-[#6b6b80]">실패</p>
                        <p className="font-semibold text-[#111118]">
                          {config.embedding.job_counts.failed}
                        </p>
                      </div>
                    </div>
                  </div>

                  <div className="rounded-xl border border-[rgba(0,0,0,0.08)] p-4 bg-[#f8f8fb]">
                    <div className="flex items-center justify-between mb-3">
                      <p className="text-sm font-semibold text-[#111118]">연결 테스트</p>
                      <Button
                        variant="secondary"
                        size="sm"
                        loading={embTesting}
                        icon={!embTesting ? <Wifi className="w-3.5 h-3.5" /> : undefined}
                        onClick={() => void runEmbTest()}
                      >
                        테스트 실행
                      </Button>
                    </div>
                    {embTest?.status === "OK" && (
                      <InlineAlert type="success" title="연결 정상">
                        {embTest.provider} · {embTest.model} · dim {embTest.dimension} ·{" "}
                        {embTest.latency_ms}ms
                      </InlineAlert>
                    )}
                    {embTest?.status === "NOT_CONFIGURED" && (
                      <InlineAlert type="warning" title="미구성">
                        {embTest.safe_message ??
                          embTest.error_code ??
                          "임베딩이 구성되지 않았습니다."}
                      </InlineAlert>
                    )}
                    {embTest?.status === "ERROR" && (
                      <InlineAlert type="error" title="연결 실패">
                        {embTest.safe_message ?? embTest.error_code ?? "오류"}
                      </InlineAlert>
                    )}
                    {!embTest && !embTesting && (
                      <p className="text-xs text-[#9ca3af]">
                        테스트를 실행하면 임베딩 연결 상태를 확인합니다.
                      </p>
                    )}
                  </div>

                  <RecentAuditPanel items={auditItems} loading={auditLoading} />
                </div>
              )}

              <div className="flex justify-end mt-6">
                <Button
                  variant="secondary"
                  size="sm"
                  icon={<RefreshCw className="w-3.5 h-3.5" />}
                  onClick={() => {
                    if (dirty) {
                      if (
                        !window.confirm(
                          "저장하지 않은 변경사항이 있습니다. 새로고침하면 편집이 취소됩니다.",
                        )
                      ) {
                        return;
                      }
                      setEditing(false);
                    }
                    void loadConfig();
                    void loadAudit(tab);
                  }}
                >
                  새로고침
                </Button>
              </div>
            </div>
          </div>
        </>
      )}

      <ConfirmDialog
        open={resetConfirmOpen}
        onClose={() => !resetting && setResetConfirmOpen(false)}
        onConfirm={() => void confirmReset()}
        title="환경값으로 되돌리기"
        description="저장된 Runtime 설정을 삭제하고 서버 환경변수 값을 다시 사용합니다. 계속하시겠습니까?"
        confirmLabel={resetting ? "처리 중..." : "되돌리기"}
        variant="danger"
        loading={resetting}
      />
    </AdminShell>
  );
}
