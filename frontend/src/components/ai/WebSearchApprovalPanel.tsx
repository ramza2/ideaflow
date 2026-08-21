import { useState } from "react";
import { X, Globe, ShieldCheck, ChevronDown, ChevronUp, Pencil, Check } from "lucide-react";
import { Button } from "../common/Button";
import { toast } from "../common/Toast";

interface SearchTarget {
  id: string;
  label: string;
  queries: string[];
  selected: boolean;
}

interface WebSearchApprovalPanelProps {
  open: boolean;
  onClose: () => void;
  onApprove: (targets: SearchTarget[]) => void;
  onSkip: () => void;
}

const INITIAL_TARGETS: SearchTarget[] = [
  {
    id: "similar",
    label: "유사 서비스",
    queries: ["MCP agent collaboration network", "AI agent marketplace open source"],
    selected: true,
  },
  {
    id: "tech",
    label: "기술 사례",
    queries: ["Model Context Protocol implementation examples", "multi-agent trust model design"],
    selected: true,
  },
  {
    id: "legal",
    label: "개인정보·법률 고려사항",
    queries: ["AI agent data privacy regulations", "federated AI legal compliance 2026"],
    selected: false,
  },
  {
    id: "market",
    label: "시장 현황",
    queries: ["AI agent network market size 2026", "enterprise multi-agent adoption rate"],
    selected: true,
  },
];

const REASON = "아이디어에 '유사 서비스', '기술 사례', '시장 현황' 항목이 포함되어 있어 외부 자료로 보완하면 초안의 완성도를 높일 수 있습니다.";

const PREVIEW_CONTENT = [
  "MCP 협업 네트워크 아이디어 (구체적 회사명·인물명 제외)",
  "핵심 문제 요약: AI 에이전트 간 표준화된 협업 부재",
  "검색 대상 분야: 유사 서비스, 기술 구현 사례, 시장 규모",
];

export function WebSearchApprovalPanel({
  open,
  onClose,
  onApprove,
  onSkip,
}: WebSearchApprovalPanelProps) {
  const [targets, setTargets] = useState<SearchTarget[]>(INITIAL_TARGETS);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [editQueries, setEditQueries] = useState<string>("");
  const [showPreview, setShowPreview] = useState(false);
  const [maskingExpanded, setMaskingExpanded] = useState(false);

  if (!open) return null;

  function toggleTarget(id: string) {
    setTargets((prev) =>
      prev.map((t) => (t.id === id ? { ...t, selected: !t.selected } : t))
    );
  }

  function startEdit(t: SearchTarget) {
    setEditingId(t.id);
    setEditQueries(t.queries.join("\n"));
  }

  function saveEdit(id: string) {
    setTargets((prev) =>
      prev.map((t) =>
        t.id === id
          ? { ...t, queries: editQueries.split("\n").map((q) => q.trim()).filter(Boolean) }
          : t
      )
    );
    setEditingId(null);
  }

  function handleApprove() {
    const selected = targets.filter((t) => t.selected);
    if (selected.length === 0) {
      toast.warning("검색 대상을 하나 이상 선택해 주세요");
      return;
    }
    onApprove(selected);
    toast.info(`웹 검색을 시작합니다`, `${selected.length}개 항목 검색 중...`);
  }

  const selectedCount = targets.filter((t) => t.selected).length;

  return (
    <div className="fixed inset-0 bg-black/30 z-50 flex items-center justify-center p-4">
      <div
        className="bg-white rounded-2xl border border-[rgba(0,0,0,0.08)] shadow-2xl w-full max-w-lg flex flex-col max-h-[90vh]"
        onClick={(e) => e.stopPropagation()}
      >
        {/* Header */}
        <div className="flex items-start justify-between px-6 pt-6 pb-4 border-b border-[rgba(0,0,0,0.06)] shrink-0">
          <div className="flex items-start gap-3">
            <div className="w-9 h-9 rounded-xl bg-[#dbeafe] flex items-center justify-center shrink-0 mt-0.5">
              <Globe className="w-4.5 h-4.5 text-[#2563eb]" />
            </div>
            <div>
              <h2 className="text-base font-bold text-[#111118]">외부 자료를 검색해 초안을 보완할까요?</h2>
              <p className="text-sm text-[#6b6b80] mt-0.5">검색 전 아래 내용을 확인하고 승인해 주세요.</p>
            </div>
          </div>
          <button
            onClick={onClose}
            className="w-7 h-7 flex items-center justify-center rounded-lg text-[#9ca3af] hover:bg-[#f4f4f8] hover:text-[#6b6b80] shrink-0 mt-0.5"
          >
            <X className="w-4 h-4" />
          </button>
        </div>

        <div className="flex-1 overflow-y-auto px-6 py-4 space-y-5">
          {/* Reason */}
          <div className="rounded-xl bg-[#eff6ff] border border-[#bfdbfe] p-4">
            <p className="text-xs font-semibold text-[#1d4ed8] mb-1.5">검색이 필요한 이유</p>
            <p className="text-sm text-[#1e40af] leading-relaxed">{REASON}</p>
          </div>

          {/* Search targets */}
          <div>
            <p className="text-xs font-semibold text-[#6b6b80] uppercase tracking-wider mb-3">검색 대상 및 검색어</p>
            <div className="space-y-2">
              {targets.map((t) => (
                <div
                  key={t.id}
                  className={`rounded-xl border p-3.5 transition-colors ${
                    t.selected
                      ? "border-[#4f46e5]/30 bg-[#f5f3ff]"
                      : "border-[rgba(0,0,0,0.08)] bg-[#fafafa]"
                  }`}
                >
                  <div className="flex items-center gap-3">
                    <input
                      type="checkbox"
                      checked={t.selected}
                      onChange={() => toggleTarget(t.id)}
                      className="w-4 h-4 accent-[#4f46e5] shrink-0"
                    />
                    <span className={`text-sm font-medium flex-1 ${t.selected ? "text-[#111118]" : "text-[#9ca3af]"}`}>
                      {t.label}
                    </span>
                    {t.selected && (
                      <button
                        onClick={() => startEdit(t)}
                        className="w-6 h-6 flex items-center justify-center rounded-md text-[#9ca3af] hover:text-[#4f46e5] hover:bg-[#ede9fe] transition-colors"
                      >
                        <Pencil className="w-3.5 h-3.5" />
                      </button>
                    )}
                  </div>

                  {t.selected && editingId === t.id ? (
                    <div className="mt-2 ml-7">
                      <textarea
                        value={editQueries}
                        onChange={(e) => setEditQueries(e.target.value)}
                        className="w-full h-20 rounded-lg border border-[#4f46e5] bg-white px-3 py-2 text-xs text-[#111118] font-mono resize-none focus:outline-none focus:ring-2 focus:ring-[#4f46e5]/20"
                        placeholder="검색어를 줄바꿈으로 구분해 입력하세요"
                      />
                      <div className="flex gap-2 mt-1.5">
                        <Button variant="primary" size="sm" onClick={() => saveEdit(t.id)} icon={<Check className="w-3 h-3" />}>저장</Button>
                        <Button variant="ghost" size="sm" onClick={() => setEditingId(null)}>취소</Button>
                      </div>
                    </div>
                  ) : t.selected ? (
                    <div className="mt-2 ml-7 space-y-1">
                      {t.queries.map((q, i) => (
                        <p key={i} className="text-xs text-[#6b6b80] font-mono bg-white/70 rounded px-2 py-0.5">
                          {q}
                        </p>
                      ))}
                    </div>
                  ) : null}
                </div>
              ))}
            </div>
          </div>

          {/* What gets sent */}
          <div>
            <button
              onClick={() => setShowPreview(!showPreview)}
              className="flex items-center gap-2 text-xs font-semibold text-[#6b6b80] uppercase tracking-wider hover:text-[#111118] transition-colors w-full"
            >
              <ShieldCheck className="w-3.5 h-3.5 text-[#16a34a]" />
              외부로 전달되는 내용
              {showPreview ? <ChevronUp className="w-3.5 h-3.5 ml-auto" /> : <ChevronDown className="w-3.5 h-3.5 ml-auto" />}
            </button>
            {showPreview && (
              <div className="mt-2 rounded-xl bg-[#f0fdf4] border border-[#bbf7d0] p-4">
                <p className="text-xs font-medium text-[#15803d] mb-2">전달 내용 (민감정보 자동 제거됨)</p>
                <ul className="space-y-1">
                  {PREVIEW_CONTENT.map((item, i) => (
                    <li key={i} className="text-xs text-[#166534] flex items-start gap-1.5">
                      <Check className="w-3 h-3 shrink-0 mt-0.5" />
                      {item}
                    </li>
                  ))}
                </ul>
                <p className="text-xs text-[#9ca3af] mt-3 pt-3 border-t border-[#bbf7d0]">
                  실명, 이메일, 전화번호, IP 주소 등 개인식별정보는 검색 전 자동으로 제거됩니다.
                </p>
              </div>
            )}
          </div>
        </div>

        {/* Footer */}
        <div className="px-6 py-4 border-t border-[rgba(0,0,0,0.06)] shrink-0">
          <div className="flex items-center justify-between mb-3">
            <p className="text-xs text-[#9ca3af]">
              {selectedCount > 0 ? `${selectedCount}개 항목 검색 예정` : "검색 대상을 선택해 주세요"}
            </p>
          </div>
          <div className="flex gap-2">
            <Button variant="ghost" className="flex-1" onClick={onSkip}>웹 검색 없이 계속</Button>
            <Button
              variant="primary"
              className="flex-1"
              icon={<Globe className="w-3.5 h-3.5" />}
              disabled={selectedCount === 0}
              onClick={handleApprove}
            >
              검색 실행
            </Button>
          </div>
        </div>
      </div>
    </div>
  );
}
