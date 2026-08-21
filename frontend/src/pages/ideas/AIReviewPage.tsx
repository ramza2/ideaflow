import { useState } from "react";
import { useNavigate, useParams } from "react-router";
import { clsx } from "clsx";
import {
  Sparkles,
  ChevronDown,
  ChevronUp,
  RefreshCw,
  BookOpen,
  X,
  Check,
  AlertTriangle,
  Info,
  Pencil,
  Save,
  ArrowLeft,
} from "lucide-react";
import { Button } from "../../components/common/Button";
import { SourceBadge } from "../../components/common/Badge";
import { ProgressStepper } from "../../components/common/EmptyState";
import { toast } from "../../components/common/Toast";
import { MOCK_EVIDENCE } from "../../mocks/evidence";
import type { SourceBadgeType } from "../../types";

interface DraftField {
  key: string;
  label: string;
  value: string;
  source: SourceBadgeType;
  confidence: "clear" | "inferred" | "needs_check" | "insufficient";
}

const INITIAL_DRAFT: DraftField[] = [
  { key: "title", label: "아이디어명", value: "글로벌 MCP 협업 네트워크", source: "llm_structured", confidence: "clear" },
  { key: "oneLiner", label: "한 줄 정의", value: "전 세계 AI 에이전트가 MCP 프로토콜로 협업하는 오픈 네트워크 플랫폼", source: "llm_structured", confidence: "clear" },
  { key: "field", label: "대표 분야", value: "기술/AI", source: "llm_inferred", confidence: "inferred" },
  { key: "tags", label: "태그", value: "AI, MCP, 협업, 오픈소스, 에이전트", source: "llm_structured", confidence: "clear" },
  { key: "background", label: "배경", value: "AI 에이전트들이 격리된 환경에서 작동하고 있어 협업이 어렵다. MCP는 표준 프로토콜로 이를 해결할 수 있는 잠재력이 있다.", source: "user_input", confidence: "clear" },
  { key: "problem", label: "해결하려는 문제", value: "AI 에이전트 간 데이터 공유 및 작업 위임이 표준화되어 있지 않아 각각의 사일로에서 운영된다.", source: "llm_structured", confidence: "clear" },
  { key: "concept", label: "핵심 개념", value: "MCP 프로토콜을 기반으로 에이전트가 서로 작업을 요청하고 결과를 공유하는 글로벌 네트워크 구축", source: "llm_inferred", confidence: "inferred" },
  { key: "features", label: "주요 기능", value: "에이전트 등록 레지스트리, 작업 위임 API, 결과 검증 시스템, 신뢰 점수 체계", source: "web_evidence", confidence: "needs_check" },
  { key: "expectedEffect", label: "기대 효과", value: "AI 생태계 전반의 협업 효율 향상, 중복 개발 감소, 전문화된 에이전트 활용 가능", source: "llm_inferred", confidence: "inferred" },
  { key: "targetUsers", label: "예상 사용자", value: "AI 개발자, 기업 AI 팀, 오픈소스 기여자", source: "llm_structured", confidence: "clear" },
  { key: "challenges", label: "주요 난제", value: "신뢰 모델 설계, 프라이버시 보호, 네트워크 확장성", source: "llm_inferred", confidence: "needs_check" },
  { key: "validation", label: "최소 검증 방법", value: "소규모 폐쇄 베타로 3개 팀 간 에이전트 협업 시나리오 검증", source: "llm_inferred", confidence: "inferred" },
];

const CONFIDENCE_CONFIG: Record<string, { label: string; icon: React.ReactNode; className: string }> = {
  clear: { label: "명확", icon: <Check className="w-3 h-3" />, className: "text-[#16a34a] bg-[#f0fdf4]" },
  inferred: { label: "추론 포함", icon: <Info className="w-3 h-3" />, className: "text-[#d97706] bg-[#fffbeb]" },
  needs_check: { label: "확인 필요", icon: <AlertTriangle className="w-3 h-3" />, className: "text-[#dc2626] bg-[#fef2f2]" },
  insufficient: { label: "정보 부족", icon: <AlertTriangle className="w-3 h-3" />, className: "text-[#9ca3af] bg-[#f0f0f5]" },
};

export function AIReviewPage() {
  const navigate = useNavigate();
  const { workspaceId = "personal" } = useParams();
  const [draft, setDraft] = useState<DraftField[]>(INITIAL_DRAFT);
  const [editingKey, setEditingKey] = useState<string | null>(null);
  const [editValue, setEditValue] = useState("");
  const [originalOpen, setOriginalOpen] = useState(true);
  const [showEvidence, setShowEvidence] = useState(true);
  const [showConfirmModal, setShowConfirmModal] = useState(false);

  function startEdit(field: DraftField) {
    setEditingKey(field.key);
    setEditValue(field.value);
  }

  function saveEdit(key: string) {
    setDraft((prev) =>
      prev.map((f) =>
        f.key === key ? { ...f, value: editValue, source: "user_edited" } : f
      )
    );
    setEditingKey(null);
  }

  function handleRegister() {
    setShowConfirmModal(true);
  }

  function confirmRegister() {
    setShowConfirmModal(false);
    toast.success("아이디어가 등록되었습니다 🎉", "IF-011 · 글로벌 MCP 협업 네트워크");
    navigate(`/w/${workspaceId}/ideas/idea-001`);
  }

  const basicFields = draft.slice(0, 4);
  const contentFields = draft.slice(4, 11);
  const mgmtFields = draft.slice(11);

  return (
    <div className="flex flex-col h-full">
      {/* Header bar */}
      <div className="px-4 sm:px-8 py-4 bg-white border-b border-[rgba(0,0,0,0.06)]">
        <div className="flex items-center justify-between mb-3">
          <ProgressStepper
            steps={["아이디어 입력", "AI 분석", "초안 검토", "등록 완료"]}
            current={2}
          />
        </div>
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-lg font-bold text-[#111118]">AI 등록 초안 검토</h1>
            <p className="text-sm text-[#6b6b80]">AI가 정리한 내용을 확인하고 필요한 경우 수정하세요.</p>
          </div>
        </div>
      </div>

      <div className="flex flex-1 overflow-hidden">
        {/* Left: original text */}
        <div className="w-64 border-r border-[rgba(0,0,0,0.06)] bg-[#fafafa] flex flex-col overflow-hidden shrink-0 hidden lg:flex">
          <div className="flex items-center justify-between px-4 py-3 border-b border-[rgba(0,0,0,0.06)]">
            <p className="text-xs font-semibold text-[#6b6b80] uppercase tracking-wider">사용자 원문</p>
            <button onClick={() => setOriginalOpen(!originalOpen)}>
              {originalOpen ? <ChevronUp className="w-4 h-4 text-[#9ca3af]" /> : <ChevronDown className="w-4 h-4 text-[#9ca3af]" />}
            </button>
          </div>
          <div className="flex-1 overflow-y-auto p-4">
            <p className="text-xs text-[#6b6b80] leading-relaxed">
              AI 에이전트들이 각각의 사일로에서 동작하고 있는데, 만약 전 세계 AI 에이전트들이 MCP 같은 표준 프로토콜로 서로 협업할 수 있다면 어떨까? 에이전트 레지스트리가 있고, 작업을 위임할 수 있고, 결과를 공유하는 오픈 네트워크. 신뢰 문제가 핵심 난제일 것 같음.
            </p>
            <div className="mt-4 border-t border-[rgba(0,0,0,0.06)] pt-4">
              <p className="text-xs font-medium text-[#6b6b80] mb-2">추가 질문 답변</p>
              <p className="text-xs text-[#9ca3af]">주 사용자: AI 개발자, 기업 팀</p>
            </div>
          </div>
        </div>

        {/* Center: draft fields */}
        <div className="flex-1 overflow-y-auto px-6 py-5">
          <FieldSection title="기본정보" fields={basicFields} editingKey={editingKey} editValue={editValue} onEdit={startEdit} onSave={saveEdit} onEditChange={setEditValue} onCancelEdit={() => setEditingKey(null)} />
          <FieldSection title="아이디어 내용" fields={contentFields} editingKey={editingKey} editValue={editValue} onEdit={startEdit} onSave={saveEdit} onEditChange={setEditValue} onCancelEdit={() => setEditingKey(null)} />
          <FieldSection title="관리정보" fields={mgmtFields} editingKey={editingKey} editValue={editValue} onEdit={startEdit} onSave={saveEdit} onEditChange={setEditValue} onCancelEdit={() => setEditingKey(null)} />

          {/* Similar ideas */}
          <div className="mt-6 bg-[#fffbeb] rounded-xl border border-[#fde68a] p-4">
            <p className="text-sm font-semibold text-[#b45309] mb-3">⚠ 유사 아이디어 발견</p>
            <div className="bg-white rounded-lg border border-[rgba(0,0,0,0.07)] p-3 mb-3">
              <p className="text-sm font-medium text-[#111118]">IdeaFlow (IF-002)</p>
              <p className="text-xs text-[#6b6b80] mb-1">유사 이유: AI 기반 아이디어 관리 및 협업 기능 중복</p>
              <div className="w-full bg-[#f0f0f5] rounded-full h-1.5 mb-2">
                <div className="h-1.5 rounded-full bg-[#d97706]" style={{ width: "42%" }} />
              </div>
              <p className="text-xs text-[#9ca3af]">유사도 42%</p>
            </div>
            <div className="flex flex-wrap gap-2">
              {["별도 아이디어로 등록", "기존 아이디어에 추가", "두 아이디어 연결", "등록 취소"].map((opt) => (
                <Button key={opt} variant="secondary" size="sm">{opt}</Button>
              ))}
            </div>
          </div>
        </div>

        {/* Right: evidence */}
        {showEvidence && (
          <div className="w-72 border-l border-[rgba(0,0,0,0.06)] flex flex-col overflow-hidden shrink-0 hidden xl:flex">
            <div className="flex items-center justify-between px-4 py-3 border-b border-[rgba(0,0,0,0.06)]">
              <p className="text-xs font-semibold text-[#6b6b80] uppercase tracking-wider">근거·출처</p>
              <button onClick={() => setShowEvidence(false)}>
                <X className="w-4 h-4 text-[#9ca3af]" />
              </button>
            </div>
            <div className="flex-1 overflow-y-auto p-4 space-y-3">
              {MOCK_EVIDENCE.slice(0, 3).map((ev) => (
                <div key={ev.id} className="bg-white rounded-lg border border-[rgba(0,0,0,0.07)] p-3">
                  <p className="text-xs font-semibold text-[#111118] mb-1 line-clamp-2">{ev.title}</p>
                  <p className="text-xs text-[#9ca3af] mb-2">{ev.publisher}</p>
                  <p className="text-xs text-[#6b6b80] line-clamp-3">{ev.summary}</p>
                  <div className="flex gap-1 mt-2 flex-wrap">
                    {ev.relatedFields.map((f) => (
                      <span key={f} className="text-[10px] px-1.5 py-0.5 rounded bg-[#ede9fe] text-[#7c3aed]">{f}</span>
                    ))}
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}
      </div>

      {/* Bottom action bar */}
      <div className="px-4 sm:px-8 py-4 bg-white border-t border-[rgba(0,0,0,0.06)] flex flex-wrap items-center gap-2 sm:gap-3">
        <Button variant="ghost" icon={<ArrowLeft className="w-4 h-4" />} onClick={() => navigate(-1)}>이전</Button>
        <Button variant="secondary">임시 저장</Button>
        <div className="ml-auto flex items-center gap-2">
          <Button variant="ghost" icon={<RefreshCw className="w-3.5 h-3.5" />}>전체 다시 생성</Button>
          <Button variant="secondary" icon={<Pencil className="w-3.5 h-3.5" />}>직접 수정 모드</Button>
          <Button variant="primary" icon={<Check className="w-4 h-4" />} onClick={handleRegister}>
            아이디어 등록
          </Button>
        </div>
      </div>

      {/* Confirm modal */}
      {showConfirmModal && (
        <div className="fixed inset-0 bg-black/30 z-50 flex items-center justify-center p-4">
          <div className="bg-white rounded-2xl border border-[rgba(0,0,0,0.08)] shadow-xl w-full max-w-sm p-6">
            <div className="flex items-center gap-2 mb-3">
              <Sparkles className="w-5 h-5 text-[#4f46e5]" />
              <h3 className="text-base font-bold text-[#111118]">아이디어를 등록하시겠습니까?</h3>
            </div>
            <p className="text-sm text-[#6b6b80] mb-5">
              검토된 내용으로 아이디어가 등록됩니다. 등록 후에도 편집이 가능합니다.
            </p>
            <div className="flex gap-2">
              <Button variant="ghost" className="flex-1" onClick={() => setShowConfirmModal(false)}>취소</Button>
              <Button variant="primary" className="flex-1" onClick={confirmRegister}>등록</Button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

function FieldSection({
  title,
  fields,
  editingKey,
  editValue,
  onEdit,
  onSave,
  onEditChange,
  onCancelEdit,
}: {
  title: string;
  fields: DraftField[];
  editingKey: string | null;
  editValue: string;
  onEdit: (f: DraftField) => void;
  onSave: (key: string) => void;
  onEditChange: (v: string) => void;
  onCancelEdit: () => void;
}) {
  const CONFIDENCE_CONFIG: Record<string, { label: string; className: string }> = {
    clear: { label: "명확", className: "text-[#16a34a] bg-[#f0fdf4]" },
    inferred: { label: "추론 포함", className: "text-[#d97706] bg-[#fffbeb]" },
    needs_check: { label: "확인 필요", className: "text-[#dc2626] bg-[#fef2f2]" },
    insufficient: { label: "정보 부족", className: "text-[#9ca3af] bg-[#f0f0f5]" },
  };

  return (
    <div className="mb-6">
      <h3 className="text-xs font-semibold text-[#6b6b80] uppercase tracking-wider mb-3">{title}</h3>
      <div className="bg-white rounded-xl border border-[rgba(0,0,0,0.07)] divide-y divide-[rgba(0,0,0,0.05)]">
        {fields.map((field) => {
          const isEditing = editingKey === field.key;
          const conf = CONFIDENCE_CONFIG[field.confidence];
          return (
            <div key={field.key} className="p-4 group">
              <div className="flex items-center gap-2 mb-1.5">
                <span className="text-xs font-semibold text-[#6b6b80]">{field.label}</span>
                <SourceBadge type={field.source} />
                <span className={clsx("text-[10px] px-1.5 py-0.5 rounded-full font-medium", conf.className)}>
                  {conf.label}
                </span>
                <div className="ml-auto flex items-center gap-1 opacity-0 group-hover:opacity-100 transition-opacity">
                  <button
                    onClick={() => onEdit(field)}
                    className="p-1 rounded hover:bg-[#f0f0f5] text-[#6b6b80]"
                  >
                    <Pencil className="w-3 h-3" />
                  </button>
                  <button className="p-1 rounded hover:bg-[#f0f0f5] text-[#6b6b80]">
                    <RefreshCw className="w-3 h-3" />
                  </button>
                  <button className="p-1 rounded hover:bg-[#f0f0f5] text-[#6b6b80]">
                    <BookOpen className="w-3 h-3" />
                  </button>
                </div>
              </div>
              {isEditing ? (
                <div>
                  <textarea
                    value={editValue}
                    onChange={(e) => onEditChange(e.target.value)}
                    className="w-full rounded-lg border border-[#4f46e5] bg-white px-3 py-2 text-sm text-[#111118] resize-none focus:outline-none focus:ring-2 focus:ring-[#4f46e5]/20 min-h-[60px]"
                    autoFocus
                  />
                  <div className="flex gap-2 mt-2">
                    <Button variant="primary" size="sm" onClick={() => onSave(field.key)}>저장</Button>
                    <Button variant="ghost" size="sm" onClick={onCancelEdit}>취소</Button>
                  </div>
                </div>
              ) : (
                <p className="text-sm text-[#111118] leading-relaxed">{field.value}</p>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}
