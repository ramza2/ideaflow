import { useEffect, useState } from "react";
import { X, Globe, ShieldCheck, ChevronDown, ChevronUp, Plus, Trash2, Check, Loader2 } from "lucide-react";
import { Button } from "../common/Button";
import type { WebResearchRun } from "../../types/api";

interface WebSearchApprovalPanelProps {
  open: boolean;
  onClose: () => void;
  initialQueries: string[];
  previewRun: WebResearchRun | null;
  loadingPreview: boolean;
  approving: boolean;
  error: string | null;
  onQueriesChange: (queries: string[]) => void;
  onPreview: () => void;
  onApprove: () => void;
  onCancel: () => void;
}

export function WebSearchApprovalPanel({
  open,
  onClose,
  initialQueries,
  previewRun,
  loadingPreview,
  approving,
  error,
  onQueriesChange,
  onPreview,
  onApprove,
  onCancel,
}: WebSearchApprovalPanelProps) {
  const [queries, setQueries] = useState<string[]>([]);
  const [showPrivacy, setShowPrivacy] = useState(true);
  const [step, setStep] = useState<"edit" | "confirm">("edit");

  useEffect(() => {
    if (!open) return;
    setQueries(initialQueries.length > 0 ? [...initialQueries] : [""]);
    setStep(previewRun?.status === "AWAITING_APPROVAL" ? "confirm" : "edit");
  }, [open, initialQueries, previewRun?.id, previewRun?.status]);

  if (!open) return null;

  function updateQuery(index: number, value: string) {
    const next = [...queries];
    next[index] = value;
    setQueries(next);
    onQueriesChange(next.filter((q) => q.trim()));
  }

  function addQuery() {
    if (queries.length >= 5) return;
    setQueries([...queries, ""]);
  }

  function removeQuery(index: number) {
    if (queries.length <= 1) return;
    const next = queries.filter((_, i) => i !== index);
    setQueries(next);
    onQueriesChange(next.filter((q) => q.trim()));
  }

  function handlePreviewClick() {
    const trimmed = queries.map((q) => q.trim()).filter(Boolean);
    if (trimmed.length === 0) return;
    onQueriesChange(trimmed);
    onPreview();
  }

  const previewQueries = previewRun?.queries_to_send ?? [];
  const canPreview = queries.some((q) => q.trim().length > 0);

  return (
    <div className="fixed inset-0 bg-black/30 z-50 flex items-center justify-center p-4">
      <div
        className="bg-white rounded-2xl border border-[rgba(0,0,0,0.08)] shadow-2xl w-full max-w-lg flex flex-col max-h-[90vh]"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-start justify-between px-6 pt-6 pb-4 border-b border-[rgba(0,0,0,0.06)] shrink-0">
          <div className="flex items-start gap-3">
            <div className="w-9 h-9 rounded-xl bg-[#dbeafe] flex items-center justify-center shrink-0 mt-0.5">
              <Globe className="w-4.5 h-4.5 text-[#2563eb]" />
            </div>
            <div>
              <h2 className="text-base font-bold text-[#111118]">외부 자료를 검색해 초안을 보완할까요?</h2>
              <p className="text-sm text-[#6b6b80] mt-0.5">
                {step === "edit"
                  ? "검색어를 편집한 뒤 전송 내용을 확인해 주세요."
                  : "아래 검색어만 외부 검색 서비스로 전송됩니다."}
              </p>
            </div>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="w-7 h-7 flex items-center justify-center rounded-lg text-[#9ca3af] hover:bg-[#f4f4f8] hover:text-[#6b6b80] shrink-0 mt-0.5"
          >
            <X className="w-4 h-4" />
          </button>
        </div>

        <div className="flex-1 overflow-y-auto px-6 py-4 space-y-5">
          {error && (
            <div className="rounded-xl bg-[#fef2f2] border border-[#fecaca] p-3 text-sm text-[#b91c1c]">
              {error}
            </div>
          )}

          {step === "edit" ? (
            <div>
              <p className="text-xs font-semibold text-[#6b6b80] uppercase tracking-wider mb-3">
                검색어 (1~5개)
              </p>
              <div className="space-y-2">
                {queries.map((q, i) => (
                  <div key={i} className="flex gap-2">
                    <input
                      type="text"
                      value={q}
                      onChange={(e) => updateQuery(i, e.target.value)}
                      maxLength={200}
                      placeholder="검색어 입력"
                      className="flex-1 h-9 rounded-lg border border-[rgba(0,0,0,0.1)] px-3 text-sm"
                    />
                    <button
                      type="button"
                      onClick={() => removeQuery(i)}
                      disabled={queries.length <= 1}
                      className="w-9 h-9 flex items-center justify-center rounded-lg text-[#9ca3af] hover:bg-[#fef2f2] hover:text-[#dc2626] disabled:opacity-30"
                    >
                      <Trash2 className="w-4 h-4" />
                    </button>
                  </div>
                ))}
              </div>
              {queries.length < 5 && (
                <Button
                  variant="ghost"
                  size="sm"
                  className="mt-2"
                  icon={<Plus className="w-3.5 h-3.5" />}
                  onClick={addQuery}
                >
                  검색어 추가
                </Button>
              )}
            </div>
          ) : (
            <div>
              <p className="text-xs font-semibold text-[#6b6b80] uppercase tracking-wider mb-3">
                외부 검색 서비스로 전송
              </p>
              <ul className="space-y-2">
                {previewQueries.map((q) => (
                  <li
                    key={q}
                    className="flex items-start gap-2 text-sm text-[#111118] bg-[#f0fdf4] border border-[#bbf7d0] rounded-lg px-3 py-2"
                  >
                    <Check className="w-4 h-4 text-[#16a34a] shrink-0 mt-0.5" />
                    <span className="font-mono text-xs break-all">{q}</span>
                  </li>
                ))}
              </ul>
            </div>
          )}

          <div>
            <button
              type="button"
              onClick={() => setShowPrivacy(!showPrivacy)}
              className="flex items-center gap-2 text-xs font-semibold text-[#6b6b80] uppercase tracking-wider hover:text-[#111118] transition-colors w-full"
            >
              <ShieldCheck className="w-3.5 h-3.5 text-[#16a34a]" />
              개인정보 및 전송 정책
              {showPrivacy ? (
                <ChevronUp className="w-3.5 h-3.5 ml-auto" />
              ) : (
                <ChevronDown className="w-3.5 h-3.5 ml-auto" />
              )}
            </button>
            {showPrivacy && (
              <div className="mt-2 rounded-xl bg-[#f8fafc] border border-[rgba(0,0,0,0.08)] p-4 space-y-3 text-xs text-[#475569] leading-relaxed">
                <p>외부 검색 서비스에는 아래 검색어만 전송됩니다.</p>
                <p>아이디어 원문과 전체 AI 초안은 외부 검색 서비스에 전송되지 않습니다.</p>
                <p>
                  이메일·전화번호·IP 등 명확한 민감정보 형태는 서버에서 제거할 수 있지만,
                  모든 인명·회사명·민감정보를 자동 판별한다고 보장하지 않습니다.
                </p>
                <p>검색 실행 전 최종 검색어를 직접 확인해 주세요.</p>
                <div className="pt-2 border-t border-[rgba(0,0,0,0.06)] space-y-1">
                  <p className="font-medium text-[#334155]">전송하지 않음</p>
                  <ul className="space-y-0.5">
                    {["아이디어 원문", "전체 AI 초안", "사용자 이메일", "Workspace 정보"].map(
                      (item) => (
                        <li key={item} className="flex items-center gap-1.5">
                          <Check className="w-3 h-3 text-[#9ca3af]" />
                          {item}
                        </li>
                      ),
                    )}
                  </ul>
                </div>
              </div>
            )}
          </div>
        </div>

        <div className="px-6 py-4 border-t border-[rgba(0,0,0,0.06)] shrink-0">
          <div className="flex gap-2">
            {step === "edit" ? (
              <>
                <Button variant="ghost" className="flex-1" onClick={onCancel}>
                  취소
                </Button>
                <Button
                  variant="primary"
                  className="flex-1"
                  disabled={!canPreview || loadingPreview}
                  icon={
                    loadingPreview ? (
                      <Loader2 className="w-3.5 h-3.5 animate-spin" />
                    ) : (
                      <ShieldCheck className="w-3.5 h-3.5" />
                    )
                  }
                  onClick={handlePreviewClick}
                >
                  전송 내용 확인
                </Button>
              </>
            ) : (
              <>
                <Button
                  variant="ghost"
                  className="flex-1"
                  onClick={() => setStep("edit")}
                  disabled={approving}
                >
                  검색어 수정
                </Button>
                <Button
                  variant="primary"
                  className="flex-1"
                  disabled={approving || !previewRun}
                  icon={
                    approving ? (
                      <Loader2 className="w-3.5 h-3.5 animate-spin" />
                    ) : (
                      <Globe className="w-3.5 h-3.5" />
                    )
                  }
                  onClick={onApprove}
                >
                  검색 실행
                </Button>
              </>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
