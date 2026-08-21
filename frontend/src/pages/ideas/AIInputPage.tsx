import { useState } from "react";
import { useNavigate, useParams, useLocation } from "react-router";
import { clsx } from "clsx";
import {
  Sparkles,
  Paperclip,
  Globe,
  AlertTriangle,
  X,
} from "lucide-react";
import { Button } from "../../components/common/Button";
import { Select } from "../../components/common/Input";
import { Checkbox } from "../../components/common/Input";
import { ProgressStepper } from "../../components/common/EmptyState";
import { InlineAlert } from "../../components/common/EmptyState";

const ANALYSIS_OPTIONS = [
  { id: "similar", label: "유사 아이디어 확인", defaultChecked: true },
  { id: "webSearch", label: "외부 웹 검색으로 보완", defaultChecked: false },
  { id: "validation", label: "최소 검증 방법 제안", defaultChecked: true },
  { id: "counterpoint", label: "반대 관점 검토", defaultChecked: false },
  { id: "risk", label: "위험요소 분석", defaultChecked: false },
];

export function AIInputPage() {
  const navigate = useNavigate();
  const { workspaceId = "personal" } = useParams();
  const location = useLocation();
  const initialText = (location.state as any)?.text ?? "";

  const [text, setText] = useState(initialText);
  const [workspace, setWorkspace] = useState("personal");
  const [visibility, setVisibility] = useState("workspace");
  const [options, setOptions] = useState<Record<string, boolean>>(
    Object.fromEntries(ANALYSIS_OPTIONS.map((o) => [o.id, o.defaultChecked]))
  );
  const [webWarning, setWebWarning] = useState(false);

  function toggleOption(id: string) {
    const next = !options[id];
    setOptions((prev) => ({ ...prev, [id]: next }));
    if (id === "webSearch") setWebWarning(next);
  }

  function handleSubmit() {
    navigate(`/w/${workspaceId}/ideas/new/ai/analyzing`, { state: { text, options } });
  }

  return (
    <div className="min-h-full px-4 sm:px-8 py-8 max-w-[800px] mx-auto">
      {/* Stepper */}
      <div className="mb-8">
        <ProgressStepper
          steps={["아이디어 입력", "AI 분석", "초안 검토", "등록 완료"]}
          current={0}
        />
      </div>

      <div className="mb-6">
        <div className="flex items-center gap-2 mb-1">
          <Sparkles className="w-5 h-5 text-[#7c3aed]" />
          <h1 className="text-xl font-bold text-[#111118]">AI로 아이디어 등록</h1>
        </div>
        <p className="text-sm text-[#6b6b80]">
          아이디어를 정해진 형식에 맞출 필요 없이 생각나는 대로 작성하세요.
        </p>
      </div>

      <div className="space-y-6">
        {/* Settings */}
        <div className="bg-white rounded-xl border border-[rgba(0,0,0,0.07)] p-5">
          <h3 className="text-sm font-semibold text-[#111118] mb-4">기본 설정</h3>
          <div className="grid grid-cols-2 gap-4">
            <Select
              label="등록 작업공간"
              value={workspace}
              onChange={(e) => setWorkspace(e.target.value)}
              options={[
                { value: "personal", label: "내 작업공간" },
                { value: "team-001", label: "IdeaFlow Team" },
                { value: "team-002", label: "OpenLink Lab" },
              ]}
            />
            <Select
              label="공개 범위"
              value={visibility}
              onChange={(e) => setVisibility(e.target.value)}
              options={[
                { value: "private", label: "비공개" },
                { value: "workspace", label: "작업공간 공유" },
                { value: "specific", label: "지정 사용자 공유" },
              ]}
            />
          </div>
        </div>

        {/* Text input */}
        <div className="bg-white rounded-xl border border-[rgba(0,0,0,0.07)] p-5">
          <div className="flex items-center justify-between mb-3">
            <h3 className="text-sm font-semibold text-[#111118]">아이디어 내용</h3>
            <span className="text-xs font-mono text-[#9ca3af]">{text.length}/5000</span>
          </div>
          <textarea
            value={text}
            onChange={(e) => setText(e.target.value)}
            placeholder={`어떤 문제를 발견했는지, 누구를 위한 것인지,\n어떻게 해결하면 좋을지 자유롭게 적어보세요.\n\n완성된 문장이 아니어도 되고, 키워드만 나열해도 됩니다.`}
            className="w-full h-48 rounded-lg border border-[rgba(0,0,0,0.1)] bg-[#f8f8fb] px-4 py-3 text-sm text-[#111118] placeholder:text-[#9ca3af] resize-none focus:outline-none focus:ring-2 focus:ring-[#4f46e5]/15 focus:border-[#4f46e5] focus:bg-white transition-all"
            maxLength={5000}
          />
          <div className="flex items-center gap-2 mt-2">
            <button className="flex items-center gap-1.5 text-xs text-[#6b6b80] hover:text-[#4f46e5] transition-colors">
              <Paperclip className="w-3.5 h-3.5" />
              파일 첨부
            </button>
          </div>
        </div>

        {/* Analysis options */}
        <div className="bg-white rounded-xl border border-[rgba(0,0,0,0.07)] p-5">
          <h3 className="text-sm font-semibold text-[#111118] mb-4">분석 옵션</h3>
          <div className="space-y-3">
            {ANALYSIS_OPTIONS.map((opt) => (
              <div key={opt.id}>
                <div className="flex items-center gap-3">
                  {opt.id === "webSearch" ? (
                    <div className="flex items-center gap-2">
                      <input
                        type="checkbox"
                        id={opt.id}
                        checked={options[opt.id]}
                        onChange={() => toggleOption(opt.id)}
                        className="w-4 h-4 accent-[#4f46e5]"
                      />
                      <label htmlFor={opt.id} className="text-sm text-[#111118] flex items-center gap-1.5 cursor-pointer">
                        <Globe className="w-3.5 h-3.5 text-[#4f46e5]" />
                        {opt.label}
                        <span className="text-xs px-1.5 py-0.5 rounded bg-[#f0f0f5] text-[#6b6b80]">외부 전송 발생</span>
                      </label>
                    </div>
                  ) : (
                    <Checkbox
                      id={opt.id}
                      label={opt.label}
                      checked={options[opt.id]}
                      onChange={() => toggleOption(opt.id)}
                    />
                  )}
                </div>
              </div>
            ))}
          </div>

          {webWarning && (
            <div className="mt-4">
              <InlineAlert type="warning" title="웹 검색 안내">
                아이디어 내용의 일부가 외부 검색 서비스로 전송됩니다. 민감한 정보가 포함된 경우 마스킹 후 전송되며, 전송 전 내용을 확인하고 수정할 수 있습니다.
              </InlineAlert>
            </div>
          )}
        </div>
      </div>

      {/* Bottom action bar */}
      <div className="flex items-center justify-between mt-8 pt-6 border-t border-[rgba(0,0,0,0.06)]">
        <Button variant="ghost" onClick={() => navigate(-1)}>취소</Button>
        <div className="flex items-center gap-2">
          <Button variant="secondary">임시 저장</Button>
          <Button
            variant="ai"
            icon={<Sparkles className="w-4 h-4" />}
            disabled={!text.trim()}
            onClick={handleSubmit}
          >
            AI로 정리하기
          </Button>
        </div>
      </div>
    </div>
  );
}
