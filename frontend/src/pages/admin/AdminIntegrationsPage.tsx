import { useEffect, useState } from "react";
import { clsx } from "clsx";
import {
  Wifi,
  RefreshCw,
  Globe,
  Cpu,
  Database,
  History,
} from "lucide-react";
import { AdminShell } from "../../components/admin/AdminShell";
import { Button } from "../../components/common/Button";
import { InlineAlert } from "../../components/common/EmptyState";
import { toast } from "../../components/common/Toast";
import {
  getAdminIntegrations,
  testLlmConnection,
  testWebSearchConnection,
} from "../../api/adminIntegrations";
import { apiErrorMessage } from "../../api/client";
import type {
  AdminIntegrationConfigResponse,
  LlmConnectionTestResult,
  WebSearchConnectionTestResult,
} from "../../types/api";

type AdminTab = "llm" | "websearch" | "embedding" | "history";

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

function ReadOnlyField({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex flex-col gap-1.5">
      <label className="text-sm font-medium text-[#111118]">{label}</label>
      <input
        value={value}
        readOnly
        className="h-9 rounded-lg border border-[rgba(0,0,0,0.1)] bg-[#f8f8fb] px-3 text-sm text-[#6b6b80]"
      />
    </div>
  );
}

export function AdminIntegrationsPage() {
  const [tab, setTab] = useState<AdminTab>("llm");
  const [config, setConfig] = useState<AdminIntegrationConfigResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const [llmTest, setLlmTest] = useState<LlmConnectionTestResult | null>(null);
  const [llmTesting, setLlmTesting] = useState(false);

  const [wsTestQuery, setWsTestQuery] = useState("Python official documentation");
  const [wsTest, setWsTest] = useState<WebSearchConnectionTestResult | null>(null);
  const [wsTesting, setWsTesting] = useState(false);

  async function loadConfig() {
    setLoading(true);
    setError(null);
    try {
      const data = await getAdminIntegrations();
      setConfig(data);
    } catch (err) {
      setError(apiErrorMessage(err, "연동 설정을 불러오지 못했습니다."));
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    void loadConfig();
  }, []);

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

  const statusCards = config
    ? [
        {
          label: "LLM 설정",
          value: config.llm.api_key_configured ? "구성됨" : "API Key 미설정",
          color: config.llm.api_key_configured ? "#16a34a" : "#d97706",
        },
        {
          label: "웹 검색",
          value: config.web_search.configured ? "구성됨" : "미설정",
          color: config.web_search.configured ? "#16a34a" : "#6b6b80",
        },
        {
          label: "전역 AI",
          value: config.global_llm_enabled ? "허용" : "차단",
          color: config.global_llm_enabled ? "#16a34a" : "#dc2626",
        },
        {
          label: "전역 웹 검색",
          value: config.global_web_search_enabled ? "허용" : "차단",
          color: config.global_web_search_enabled ? "#16a34a" : "#dc2626",
        },
      ]
    : [];

  const TABS: { id: AdminTab; label: string; icon: typeof Cpu; disabled?: boolean }[] = [
    { id: "llm", label: "LLM", icon: Cpu },
    { id: "websearch", label: "웹 검색", icon: Globe },
    { id: "embedding", label: "임베딩", icon: Database, disabled: true },
    { id: "history", label: "연결 이력", icon: History, disabled: true },
  ];

  return (
    <AdminShell title="AI 및 외부 연계">
      {loading ? (
        <div className="px-8 py-12 text-center text-sm text-[#6b6b80]">불러오는 중...</div>
      ) : error ? (
        <div className="px-8 py-6">
          <InlineAlert type="error" title="오류">{error}</InlineAlert>
        </div>
      ) : (
        <>
          <div className="px-4 sm:px-8 py-5 grid grid-cols-2 sm:grid-cols-4 gap-4">
            {statusCards.map((card) => (
              <div key={card.label} className="bg-white rounded-xl border border-[rgba(0,0,0,0.07)] p-4">
                <p className="text-xs text-[#6b6b80] mb-1">{card.label}</p>
                <p className="text-base font-bold" style={{ color: card.color }}>
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
                  disabled={t.disabled}
                  title={t.disabled ? "추후 제공됩니다." : undefined}
                  onClick={() => !t.disabled && setTab(t.id)}
                  className={clsx(
                    "flex items-center gap-1.5 px-4 py-2.5 text-sm font-medium border-b-2 transition-colors",
                    t.disabled && "opacity-40 cursor-not-allowed",
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
              {tab === "llm" && config && (
                <div className="space-y-6">
                  <div>
                    <h3 className="text-base font-bold text-[#111118] mb-1">LLM 연결 설정</h3>
                    <p className="text-sm text-[#6b6b80] mb-4">
                      연결 정보는 서버 환경변수로 관리됩니다. 환경변수 변경 시 API/AI Worker 재시작이 필요합니다.
                    </p>
                    <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                      <ReadOnlyField label="Provider" value={config.llm.provider} />
                      <ReadOnlyField label="API URL" value={config.llm.api_url || "-"} />
                      <ReadOnlyField label="모델명" value={config.llm.model_name} />
                      <div className="flex flex-col gap-1.5">
                        <label className="text-sm font-medium text-[#111118]">API Key</label>
                        <ConfigBadge configured={config.llm.api_key_configured} />
                      </div>
                      <ReadOnlyField label="Timeout (초)" value={String(config.llm.timeout_seconds)} />
                      <ReadOnlyField label="최대 출력 (tokens)" value={String(config.llm.max_tokens)} />
                      <ReadOnlyField
                        label="Thinking"
                        value={config.llm.enable_thinking ? "활성" : "비활성"}
                      />
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
                      <p className="text-xs text-[#9ca3af]">테스트를 실행하면 연결 상태를 확인합니다.</p>
                    )}
                  </div>
                </div>
              )}

              {tab === "websearch" && config && (
                <div className="space-y-6">
                  <div>
                    <h3 className="text-base font-bold text-[#111118] mb-1">웹 검색 설정</h3>
                    <p className="text-sm text-[#6b6b80] mb-4">
                      연결 정보는 서버 환경변수로 관리됩니다. 환경변수 변경 시 API/AI Worker 재시작이 필요합니다.
                    </p>
                    <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                      <ReadOnlyField label="Provider" value={config.web_search.provider} />
                      <ReadOnlyField label="API URL" value={config.web_search.api_url ?? "미설정"} />
                      <div className="flex flex-col gap-1.5">
                        <label className="text-sm font-medium text-[#111118]">API Key</label>
                        <ConfigBadge configured={config.web_search.api_key_configured} />
                      </div>
                      <ReadOnlyField
                        label="결과 수 (쿼리당)"
                        value={String(config.web_search.max_results_per_query)}
                      />
                      <ReadOnlyField label="Timeout (초)" value={String(config.web_search.timeout_seconds)} />
                    </div>
                  </div>

                  <div className="rounded-xl border border-[rgba(0,0,0,0.08)] p-4 bg-[#f8f8fb]">
                    <p className="text-sm font-semibold text-[#111118] mb-1">테스트 검색</p>
                    <p className="text-xs text-[#6b6b80] mb-3">
                      입력한 테스트 검색어가 외부 검색 서비스로 전송됩니다. Idea 데이터는 전송되지 않습니다.
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
                </div>
              )}

              {tab === "embedding" && (
                <div className="py-12 text-center text-[#9ca3af]">
                  <Database className="w-8 h-8 mx-auto mb-3 opacity-50" />
                  <p className="text-sm">Semantic Search 단계에서 제공됩니다.</p>
                </div>
              )}

              {tab === "history" && (
                <div className="py-12 text-center text-[#9ca3af]">
                  <History className="w-8 h-8 mx-auto mb-3 opacity-50" />
                  <p className="text-sm">연결 테스트 이력 저장은 아직 제공되지 않습니다.</p>
                </div>
              )}

              <div className="flex justify-end mt-6">
                <Button
                  variant="secondary"
                  size="sm"
                  icon={<RefreshCw className="w-3.5 h-3.5" />}
                  onClick={() => void loadConfig()}
                >
                  새로고침
                </Button>
              </div>
            </div>
          </div>
        </>
      )}
    </AdminShell>
  );
}
