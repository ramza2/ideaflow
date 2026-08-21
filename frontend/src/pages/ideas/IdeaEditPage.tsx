import { useState } from "react";
import { useNavigate, useParams } from "react-router";
import { clsx } from "clsx";
import { Sparkles, Save, Eye, X } from "lucide-react";
import { MOCK_IDEAS } from "../../mocks/ideas";
import { Button } from "../../components/common/Button";
import { Input, TextArea, Select } from "../../components/common/Input";
import { toast } from "../../components/common/Toast";

export function IdeaEditPage() {
  const navigate = useNavigate();
  const { workspaceId = "personal", ideaId } = useParams();

  const existing = ideaId ? MOCK_IDEAS.find((i) => i.id === ideaId) : undefined;
  const isNew = !ideaId;

  const [title, setTitle] = useState(existing?.title ?? "");
  const [oneLiner, setOneLiner] = useState(existing?.oneLiner ?? "");
  const [field, setField] = useState(existing?.field ?? "기술/AI");
  const [tags, setTags] = useState(existing?.tags?.join(", ") ?? "");
  const [stage, setStage] = useState(existing?.stage ?? "draft");
  const [priority, setPriority] = useState(existing?.priority ?? "medium");
  const [feasibility, setFeasibility] = useState(existing?.feasibility ?? "unknown");
  const [visibility, setVisibility] = useState(existing?.visibility ?? "workspace");
  const [background, setBackground] = useState(existing?.background ?? "");
  const [problem, setProblem] = useState(existing?.problem ?? "");
  const [concept, setConcept] = useState(existing?.concept ?? "");
  const [features, setFeatures] = useState(existing?.features ?? "");
  const [expectedEffect, setExpectedEffect] = useState(existing?.expectedEffect ?? "");
  const [targetUsers, setTargetUsers] = useState(existing?.targetUsers ?? "");
  const [scenario, setScenario] = useState(existing?.scenario ?? "");
  const [challenges, setChallenges] = useState(existing?.challenges ?? "");
  const [validationMethod, setValidationMethod] = useState(existing?.validationMethod ?? "");

  function handleSave() {
    toast.success(isNew ? "아이디어가 등록되었습니다" : "변경사항이 저장되었습니다");
    navigate(ideaId ? `/w/${workspaceId}/ideas/${ideaId}` : `/w/${workspaceId}/ideas/idea-001`);
  }

  function handleTempSave() {
    toast.info("임시 저장되었습니다", "언제든 이어서 작성할 수 있습니다.");
  }

  const AI_ASSIST_MENU = ["AI로 초안 작성", "더 간결하게", "더 구체적으로", "문장 다듬기"];

  function AIFieldWrapper({ label, value, onChange }: { label: string; value: string; onChange: (v: string) => void }) {
    return (
      <div className="flex flex-col gap-1.5">
        <div className="flex items-center justify-between">
          <label className="text-sm font-medium text-[#111118]">{label}</label>
          <div className="flex gap-1">
            {AI_ASSIST_MENU.map((a) => (
              <button
                key={a}
                className="text-[10px] px-1.5 py-0.5 rounded border border-[#ddd6fe] text-[#7c3aed] hover:bg-[#f5f3ff] transition-colors"
              >
                {a}
              </button>
            ))}
          </div>
        </div>
        <textarea
          value={value}
          onChange={(e) => onChange(e.target.value)}
          className="w-full rounded-lg border border-[rgba(0,0,0,0.1)] bg-white px-3 py-2.5 text-sm text-[#111118] placeholder:text-[#9ca3af] resize-none focus:outline-none focus:ring-2 focus:ring-[#4f46e5]/20 focus:border-[#4f46e5] transition-colors h-24"
        />
      </div>
    );
  }

  return (
    <div className="flex flex-col h-full">
      {/* Header */}
      <div className="px-8 py-4 bg-white border-b border-[rgba(0,0,0,0.06)] flex items-center justify-between">
        <h1 className="text-lg font-bold text-[#111118]">
          {isNew ? "새 아이디어 직접 등록" : "아이디어 편집"}
        </h1>
        <button
          onClick={() => navigate(-1)}
          className="w-8 h-8 flex items-center justify-center rounded-lg text-[#6b6b80] hover:bg-[#f4f4f8]"
        >
          <X className="w-4 h-4" />
        </button>
      </div>

      {/* Content */}
      <div className="flex-1 overflow-y-auto">
        <div className="grid grid-cols-1 lg:grid-cols-[1fr_300px] gap-0 h-full">
          {/* Left: main content */}
          <div className="px-8 py-6 space-y-5 border-r border-[rgba(0,0,0,0.06)]">
            <div className="grid grid-cols-2 gap-4">
              <Input
                label="아이디어명"
                value={title}
                onChange={(e) => setTitle(e.target.value)}
                placeholder="짧고 명확하게"
              />
              <Input
                label="한 줄 정의"
                value={oneLiner}
                onChange={(e) => setOneLiner(e.target.value)}
                placeholder="핵심을 한 문장으로"
              />
            </div>
            <div className="grid grid-cols-2 gap-4">
              <Select
                label="분야"
                value={field}
                onChange={(e) => setField(e.target.value)}
                options={[
                  { value: "기술/AI", label: "기술/AI" },
                  { value: "기술/인프라", label: "기술/인프라" },
                  { value: "기술/개발", label: "기술/개발" },
                  { value: "제품/서비스", label: "제품/서비스" },
                  { value: "업무 개선", label: "업무 개선" },
                  { value: "사업/마케팅", label: "사업/마케팅" },
                  { value: "개인 프로젝트", label: "개인 프로젝트" },
                  { value: "기타", label: "기타" },
                ]}
              />
              <Input
                label="태그 (쉼표로 구분)"
                value={tags}
                onChange={(e) => setTags(e.target.value)}
                placeholder="AI, 협업, 오픈소스"
              />
            </div>
            <div className="border-t border-[rgba(0,0,0,0.06)] pt-5 space-y-5">
              <AIFieldWrapper label="배경" value={background} onChange={setBackground} />
              <AIFieldWrapper label="해결하려는 문제" value={problem} onChange={setProblem} />
              <AIFieldWrapper label="핵심 개념" value={concept} onChange={setConcept} />
              <AIFieldWrapper label="주요 기능" value={features} onChange={setFeatures} />
              <AIFieldWrapper label="기대 효과" value={expectedEffect} onChange={setExpectedEffect} />
              <AIFieldWrapper label="예상 사용자" value={targetUsers} onChange={setTargetUsers} />
              <AIFieldWrapper label="사용 시나리오" value={scenario} onChange={setScenario} />
              <AIFieldWrapper label="주요 난제" value={challenges} onChange={setChallenges} />
              <AIFieldWrapper label="최소 검증 방법" value={validationMethod} onChange={setValidationMethod} />
            </div>
          </div>

          {/* Right: meta */}
          <div className="px-6 py-6 space-y-4">
            <Select
              label="단계"
              value={stage}
              onChange={(e) => setStage(e.target.value as any)}
              options={[
                { value: "draft", label: "초안" },
                { value: "reviewing", label: "검토 중" },
                { value: "validated", label: "검증 후보" },
                { value: "executing", label: "실행 중" },
                { value: "paused", label: "보류" },
              ]}
            />
            <Select
              label="우선순위"
              value={priority}
              onChange={(e) => setPriority(e.target.value as any)}
              options={[
                { value: "high", label: "높음" },
                { value: "medium", label: "중간" },
                { value: "low", label: "낮음" },
              ]}
            />
            <Select
              label="구현 가능성"
              value={feasibility}
              onChange={(e) => setFeasibility(e.target.value as any)}
              options={[
                { value: "high", label: "높음" },
                { value: "medium", label: "중간" },
                { value: "low", label: "낮음" },
                { value: "unknown", label: "미평가" },
              ]}
            />
            <Select
              label="공개 범위"
              value={visibility}
              onChange={(e) => setVisibility(e.target.value as any)}
              options={[
                { value: "private", label: "비공개" },
                { value: "workspace", label: "작업공간 공유" },
                { value: "specific", label: "지정 사용자 공유" },
              ]}
            />
            <Input label="담당자" placeholder="담당자 검색..." />
            <Input label="다음 검토일" type="date" />
          </div>
        </div>
      </div>

      {/* Bottom action bar */}
      <div className="px-8 py-4 bg-white border-t border-[rgba(0,0,0,0.06)] flex items-center gap-2">
        <Button variant="ghost" onClick={() => navigate(-1)}>취소</Button>
        <Button variant="secondary" onClick={handleTempSave}>임시 저장</Button>
        <Button variant="ghost" icon={<Eye className="w-3.5 h-3.5" />}>미리보기</Button>
        <div className="ml-auto">
          <Button variant="primary" icon={<Save className="w-3.5 h-3.5" />} onClick={handleSave}>저장</Button>
        </div>
      </div>
    </div>
  );
}
