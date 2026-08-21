import { useState } from "react";
import { useNavigate } from "react-router";
import { clsx } from "clsx";
import {
  ChevronLeft,
  Check,
  X,
  Wifi,
  WifiOff,
  Loader2,
  Eye,
  EyeOff,
  RefreshCw,
  Settings,
  Globe,
  Cpu,
  Database,
  History,
  AlertCircle,
  CheckCircle2,
} from "lucide-react";
import { Button } from "../../components/common/Button";
import { Input, Switch } from "../../components/common/Input";
import { InlineAlert } from "../../components/common/EmptyState";

type AdminTab = "llm" | "websearch" | "embedding" | "history";

const STATUS_CARDS = [
  { label: "LLM 상태", status: "online", value: "정상", color: "#16a34a" },
  { label: "웹 검색", status: "online", value: "정상", color: "#16a34a" },
  { label: "최근 성공 호출", status: "neutral", value: "2분 전", color: "#6b6b80" },
  { label: "최근 오류", status: "warning", value: "2시간 전", color: "#d97706" },
  { label: "오늘 사용량", status: "neutral", value: "347회", color: "#4f46e5" },
];

export function AdminIntegrationsPage() {
  const navigate = useNavigate();
  const [tab, setTab] = useState<AdminTab>("llm");

  // LLM settings
  const [llmEnabled, setLlmEnabled] = useState(true);
  const [apiUrl, setApiUrl] = useState("https://alzi-llm.openlink.kr");
  const [modelName, setModelName] = useState("Qwen3-14B");
  const [apiKey, setApiKey] = useState("sk-••••••••••••••••••••••••••••••••");
  const [showApiKey, setShowApiKey] = useState(false);
  const [timeout, setTimeout_] = useState("30");
  const [maxTokens, setMaxTokens] = useState("4096");
  const [retryCount, setRetryCount] = useState("3");
  const [testStatus, setTestStatus] = useState<"idle" | "testing" | "success" | "failed">("idle");

  // Web search settings
  const [wsEnabled, setWsEnabled] = useState(true);
  const [wsProvider, setWsProvider] = useState("Tavily");
  const [wsApiUrl, setWsApiUrl] = useState("https://api.tavily.com");
  const [wsApiKey, setWsApiKey] = useState("tvly-••••••••••••••••••••••••");
  const [wsResults, setWsResults] = useState("5");
  const [wsTimeout, setWsTimeout] = useState("15");
  const [wsPriority, setWsPriority] = useState(true);
  const [wsAllowed, setWsAllowed] = useState("");
  const [wsBlocked, setWsBlocked] = useState("");

  // Policies
  const [allowManualOnFail, setAllowManualOnFail] = useState(true);
  const [limitPerWs, setLimitPerWs] = useState(false);
  const [storeInput, setStoreInput] = useState(false);
  const [maskSensitive, setMaskSensitive] = useState(true);
  const [logRetention, setLogRetention] = useState("90");

  // Web search test
  const [wsTestQuery, setWsTestQuery] = useState("");
  const [wsTestRunning, setWsTestRunning] = useState(false);

  function runLlmTest() {
    setTestStatus("testing");
    setTimeout(() => setTestStatus("success"), 2000);
  }

  function runWsTest() {
    setWsTestRunning(true);
    setTimeout(() => setWsTestRunning(false), 1500);
  }

  const TABS: { id: AdminTab; label: string; icon: any }[] = [
    { id: "llm", label: "LLM", icon: Cpu },
    { id: "websearch", label: "웹 검색", icon: Globe },
    { id: "embedding", label: "임베딩", icon: Database },
    { id: "history", label: "연결 이력", icon: History },
  ];

  return (
    <div className="min-h-full bg-[#f0f0f5]">
      {/* Admin header */}
      <div className="bg-[#111118] text-white px-4 sm:px-8 py-4">
        <div className="flex items-center gap-4">
          <button
            onClick={() => navigate(-1)}
            className="flex items-center gap-1.5 text-white/60 hover:text-white text-sm transition-colors"
          >
            <ChevronLeft className="w-4 h-4" />
            앱으로 돌아가기
          </button>
          <div className="w-px h-4 bg-white/20" />
          <div className="flex items-center gap-2">
            <Settings className="w-4 h-4 text-white/60" />
            <span className="text-sm font-medium">시스템 관리</span>
          </div>
          <span className="text-white/30">/</span>
          <span className="text-sm text-white/80">AI 및 외부 연계</span>
        </div>
      </div>

      {/* Status cards */}
      <div className="px-4 sm:px-8 py-5 grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-5 gap-4">
        {STATUS_CARDS.map((card) => (
          <div key={card.label} className="bg-white rounded-xl border border-[rgba(0,0,0,0.07)] p-4">
            <p className="text-xs text-[#6b6b80] mb-1">{card.label}</p>
            <p className="text-base font-bold" style={{ color: card.color }}>{card.value}</p>
          </div>
        ))}
      </div>

      {/* Tab navigation */}
      <div className="px-4 sm:px-8">
        <div className="bg-white rounded-t-xl border border-b-0 border-[rgba(0,0,0,0.07)] px-4 pt-2 flex gap-1 overflow-x-auto">
          {TABS.map((t) => (
            <button
              key={t.id}
              onClick={() => setTab(t.id)}
              className={clsx(
                "flex items-center gap-1.5 px-4 py-2.5 text-sm font-medium border-b-2 transition-colors",
                tab === t.id
                  ? "border-[#4f46e5] text-[#4f46e5]"
                  : "border-transparent text-[#6b6b80] hover:text-[#111118]"
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
          {/* LLM Tab */}
          {tab === "llm" && (
            <div className="space-y-8">
              {/* Connection section */}
              <div>
                <div className="flex items-center justify-between mb-5">
                  <div>
                    <h3 className="text-base font-bold text-[#111118]">LLM 연결 설정</h3>
                    <p className="text-sm text-[#6b6b80]">OpenAI Compatible API를 사용합니다.</p>
                  </div>
                  <Switch label="사용 여부" checked={llmEnabled} onChange={setLlmEnabled} />
                </div>

                <div className="grid grid-cols-1 sm:grid-cols-2 gap-4 mb-4">
                  <div className="flex flex-col gap-1.5">
                    <label className="text-sm font-medium text-[#111118]">Provider 유형</label>
                    <input value="OpenAI Compatible" readOnly className="h-9 rounded-lg border border-[rgba(0,0,0,0.1)] bg-[#f8f8fb] px-3 text-sm text-[#6b6b80]" />
                  </div>
                  <Input label="API URL" value={apiUrl} onChange={(e) => setApiUrl(e.target.value)} />
                  <Input label="모델명" value={modelName} onChange={(e) => setModelName(e.target.value)} />
                  <div className="flex flex-col gap-1.5">
                    <label className="text-sm font-medium text-[#111118]">API Key</label>
                    <div className="relative">
                      <input
                        type={showApiKey ? "text" : "password"}
                        value={apiKey}
                        onChange={(e) => setApiKey(e.target.value)}
                        className="w-full h-9 rounded-lg border border-[rgba(0,0,0,0.1)] bg-white px-3 pr-10 text-sm focus:outline-none focus:ring-2 focus:ring-[#4f46e5]/20 focus:border-[#4f46e5]"
                      />
                      <button
                        onClick={() => setShowApiKey(!showApiKey)}
                        className="absolute right-3 top-1/2 -translate-y-1/2 text-[#9ca3af]"
                      >
                        {showApiKey ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
                      </button>
                    </div>
                  </div>
                  <Input label="Timeout (초)" type="number" value={timeout} onChange={(e) => setTimeout_(e.target.value)} />
                  <Input label="최대 출력 길이 (tokens)" type="number" value={maxTokens} onChange={(e) => setMaxTokens(e.target.value)} />
                  <Input label="재시도 횟수" type="number" value={retryCount} onChange={(e) => setRetryCount(e.target.value)} />
                </div>

                {/* Connection test */}
                <div className="rounded-xl border border-[rgba(0,0,0,0.08)] p-4 bg-[#f8f8fb]">
                  <div className="flex items-center justify-between mb-3">
                    <p className="text-sm font-semibold text-[#111118]">연결 테스트</p>
                    <Button
                      variant="secondary"
                      size="sm"
                      loading={testStatus === "testing"}
                      icon={testStatus !== "testing" ? <Wifi className="w-3.5 h-3.5" /> : undefined}
                      onClick={runLlmTest}
                    >
                      테스트 실행
                    </Button>
                  </div>
                  {testStatus === "success" && (
                    <div className="space-y-2">
                      <InlineAlert type="success" title="연결 정상">API가 정상적으로 응답했습니다.</InlineAlert>
                      <div className="grid grid-cols-2 gap-3 mt-2">
                        {[
                          { label: "응답 시간", value: "847ms" },
                          { label: "확인된 모델", value: "Qwen3-14B" },
                          { label: "테스트 시각", value: new Date().toLocaleTimeString("ko") },
                          { label: "상태", value: "HTTP 200" },
                        ].map((item) => (
                          <div key={item.label}>
                            <p className="text-xs text-[#9ca3af]">{item.label}</p>
                            <p className="text-sm font-medium text-[#111118] font-mono">{item.value}</p>
                          </div>
                        ))}
                      </div>
                    </div>
                  )}
                  {testStatus === "failed" && (
                    <InlineAlert type="error" title="연결 실패">API 서버에 연결할 수 없습니다. URL과 API Key를 확인하세요.</InlineAlert>
                  )}
                  {testStatus === "idle" && (
                    <p className="text-xs text-[#9ca3af]">테스트를 실행하면 연결 상태를 확인합니다.</p>
                  )}
                </div>
              </div>

              {/* Policies */}
              <div>
                <h3 className="text-base font-bold text-[#111118] mb-4">운영 정책</h3>
                <div className="space-y-4">
                  <Switch label="LLM 장애 시 수동 등록 허용" checked={allowManualOnFail} onChange={setAllowManualOnFail} />
                  <Switch label="작업공간별 LLM 사용 제한" checked={limitPerWs} onChange={setLimitPerWs} />
                  <Switch label="입력 원문 저장" checked={storeInput} onChange={setStoreInput} />
                  <Switch label="민감정보 마스킹" checked={maskSensitive} onChange={setMaskSensitive} />
                  <div className="flex items-center gap-4">
                    <span className="text-sm text-[#111118]">호출 로그 보관 기간</span>
                    <div className="flex items-center gap-2">
                      <input
                        type="number"
                        value={logRetention}
                        onChange={(e) => setLogRetention(e.target.value)}
                        className="w-20 h-8 rounded-lg border border-[rgba(0,0,0,0.1)] bg-white px-3 text-sm focus:outline-none focus:ring-2 focus:ring-[#4f46e5]/20 focus:border-[#4f46e5]"
                      />
                      <span className="text-sm text-[#6b6b80]">일</span>
                    </div>
                  </div>
                </div>
              </div>

              <div className="flex justify-end gap-2">
                <Button variant="secondary">취소</Button>
                <Button variant="primary" icon={<Check className="w-4 h-4" />}>설정 저장</Button>
              </div>
            </div>
          )}

          {/* Web search tab */}
          {tab === "websearch" && (
            <div className="space-y-8">
              <div>
                <div className="flex items-center justify-between mb-5">
                  <div>
                    <h3 className="text-base font-bold text-[#111118]">웹 검색 설정</h3>
                    <p className="text-sm text-[#6b6b80]">아이디어 보완에 사용하는 외부 웹 검색 설정입니다.</p>
                  </div>
                  <Switch label="사용 여부" checked={wsEnabled} onChange={setWsEnabled} />
                </div>

                <div className="grid grid-cols-1 sm:grid-cols-2 gap-4 mb-4">
                  <div className="flex flex-col gap-1.5">
                    <label className="text-sm font-medium text-[#111118]">Search Provider</label>
                    <select
                      value={wsProvider}
                      onChange={(e) => setWsProvider(e.target.value)}
                      className="h-9 rounded-lg border border-[rgba(0,0,0,0.1)] bg-white px-3 text-sm focus:outline-none focus:ring-2 focus:ring-[#4f46e5]/20 focus:border-[#4f46e5]"
                    >
                      <option>Tavily</option>
                      <option>Perplexity</option>
                      <option>Brave Search</option>
                      <option>SerpAPI</option>
                    </select>
                  </div>
                  <Input label="API URL" value={wsApiUrl} onChange={(e) => setWsApiUrl(e.target.value)} />
                  <div className="flex flex-col gap-1.5">
                    <label className="text-sm font-medium text-[#111118]">API Key</label>
                    <input
                      type="password"
                      value={wsApiKey}
                      className="h-9 rounded-lg border border-[rgba(0,0,0,0.1)] bg-white px-3 text-sm focus:outline-none focus:ring-2 focus:ring-[#4f46e5]/20 focus:border-[#4f46e5]"
                    />
                  </div>
                  <Input label="기본 결과 수" type="number" value={wsResults} onChange={(e) => setWsResults(e.target.value)} />
                  <Input label="요청 제한 시간 (초)" type="number" value={wsTimeout} onChange={(e) => setWsTimeout(e.target.value)} />
                  <div className="flex flex-col gap-1.5">
                    <label className="text-sm font-medium text-[#111118]">허용 도메인 (선택)</label>
                    <input
                      value={wsAllowed}
                      onChange={(e) => setWsAllowed(e.target.value)}
                      placeholder="example.com, openlink.kr"
                      className="h-9 rounded-lg border border-[rgba(0,0,0,0.1)] bg-white px-3 text-sm placeholder:text-[#9ca3af] focus:outline-none focus:ring-2 focus:ring-[#4f46e5]/20 focus:border-[#4f46e5]"
                    />
                  </div>
                  <div className="flex flex-col gap-1.5">
                    <label className="text-sm font-medium text-[#111118]">차단 도메인 (선택)</label>
                    <input
                      value={wsBlocked}
                      onChange={(e) => setWsBlocked(e.target.value)}
                      placeholder="ads.com, spam.net"
                      className="h-9 rounded-lg border border-[rgba(0,0,0,0.1)] bg-white px-3 text-sm placeholder:text-[#9ca3af] focus:outline-none focus:ring-2 focus:ring-[#4f46e5]/20 focus:border-[#4f46e5]"
                    />
                  </div>
                </div>
                <Switch label="공식 자료 우선 검색" checked={wsPriority} onChange={setWsPriority} />

                {/* Test search */}
                <div className="mt-6 rounded-xl border border-[rgba(0,0,0,0.08)] p-4 bg-[#f8f8fb]">
                  <p className="text-sm font-semibold text-[#111118] mb-3">테스트 검색</p>
                  <div className="flex gap-2">
                    <input
                      value={wsTestQuery}
                      onChange={(e) => setWsTestQuery(e.target.value)}
                      placeholder="검색어를 입력하세요"
                      className="flex-1 h-9 rounded-lg border border-[rgba(0,0,0,0.1)] bg-white px-3 text-sm focus:outline-none focus:ring-2 focus:ring-[#4f46e5]/20 focus:border-[#4f46e5]"
                    />
                    <Button
                      variant="secondary"
                      size="sm"
                      loading={wsTestRunning}
                      onClick={runWsTest}
                    >
                      검색
                    </Button>
                  </div>
                  {!wsTestRunning && wsTestQuery && (
                    <div className="mt-3 space-y-2">
                      {["MCP protocol agent collaboration", "AI agent trust model"].map((r, i) => (
                        <div key={i} className="bg-white rounded-lg border border-[rgba(0,0,0,0.07)] p-3">
                          <p className="text-xs font-medium text-[#4f46e5] hover:underline cursor-pointer">{r} — example.com</p>
                          <p className="text-xs text-[#6b6b80] mt-0.5">샘플 검색 결과 {i + 1}번 — 실제 연결 시 결과가 표시됩니다.</p>
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              </div>

              <div className="flex justify-end gap-2">
                <Button variant="secondary">취소</Button>
                <Button variant="primary" icon={<Check className="w-4 h-4" />}>설정 저장</Button>
              </div>
            </div>
          )}

          {tab === "embedding" && (
            <div className="py-12 text-center text-[#9ca3af]">
              <Database className="w-8 h-8 mx-auto mb-3 opacity-50" />
              <p className="text-sm">임베딩 설정은 준비 중입니다.</p>
            </div>
          )}

          {tab === "history" && (
            <div className="space-y-3">
              <h3 className="text-base font-bold text-[#111118] mb-4">연결 이력</h3>
              {[
                { time: "2026-07-23 14:30", type: "LLM", status: "success", model: "Qwen3-14B", latency: "1.2s" },
                { time: "2026-07-23 14:28", type: "웹검색", status: "success", model: "Tavily", latency: "0.8s" },
                { time: "2026-07-23 12:15", type: "LLM", status: "success", model: "Qwen3-14B", latency: "2.1s" },
                { time: "2026-07-23 10:05", type: "LLM", status: "failed", model: "Qwen3-14B", latency: "timeout" },
                { time: "2026-07-23 09:30", type: "웹검색", status: "success", model: "Tavily", latency: "1.1s" },
              ].map((h, i) => (
                <div key={i} className="flex items-center gap-4 p-3 rounded-lg border border-[rgba(0,0,0,0.06)] bg-[#f8f8fb]">
                  <span
                    className={clsx(
                      "w-2 h-2 rounded-full shrink-0",
                      h.status === "success" ? "bg-[#16a34a]" : "bg-[#dc2626]"
                    )}
                  />
                  <span className="text-xs font-mono text-[#9ca3af] w-36 shrink-0">{h.time}</span>
                  <span className="text-xs px-2 py-0.5 rounded-md bg-[#ede9fe] text-[#7c3aed] shrink-0">{h.type}</span>
                  <span className="text-sm text-[#111118] flex-1">{h.model}</span>
                  <span className={clsx(
                    "text-xs font-mono",
                    h.status === "success" ? "text-[#16a34a]" : "text-[#dc2626]"
                  )}>
                    {h.latency}
                  </span>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
