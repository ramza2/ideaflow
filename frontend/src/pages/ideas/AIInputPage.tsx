import { useMemo, useState } from "react";
import { useNavigate, useParams, useLocation } from "react-router";
import { Sparkles, Check } from "lucide-react";
import { Button } from "../../components/common/Button";
import { Select } from "../../components/common/Input";
import { ProgressStepper } from "../../components/common/EmptyState";
import { InlineAlert } from "../../components/common/EmptyState";
import { toast } from "../../components/common/Toast";
import { createAiSession } from "../../api/aiSessions";
import { ApiError, apiErrorMessage } from "../../api/client";
import { useWorkspace } from "../../workspace/WorkspaceProvider";
import type { IdeaVisibility } from "../../types/api";

interface AiInputLocationState {
  text?: string;
}

export function AIInputPage() {
  const navigate = useNavigate();
  const { workspaceId = "" } = useParams();
  const location = useLocation();
  const { workspaces, currentWorkspace } = useWorkspace();

  const prefill =
    (location.state as AiInputLocationState | null)?.text?.trim() ?? "";

  const [text, setText] = useState(prefill);
  const [visibility, setVisibility] = useState<IdeaVisibility>("PRIVATE");
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [submitError, setSubmitError] = useState<string | null>(null);

  const selectedWorkspaceId = currentWorkspace?.id ?? workspaceId;
  const allowLlm = currentWorkspace?.effective_allow_llm !== false;
  const llmDisabled = currentWorkspace != null && !currentWorkspace.effective_allow_llm;

  const workspaceOptions = useMemo(
    () =>
      workspaces.map((w) => ({
        value: w.id,
        label: w.type === "PERSONAL" ? `${w.name} (개인)` : w.name,
      })),
    [workspaces],
  );

  function handleWorkspaceChange(nextId: string) {
    if (!nextId || nextId === selectedWorkspaceId) return;
    navigate(`/w/${nextId}/ideas/new/ai`, {
      replace: true,
      state: { text } satisfies AiInputLocationState,
    });
  }

  async function handleSubmit() {
    const trimmed = text.trim();
    if (!trimmed || isSubmitting || !selectedWorkspaceId || llmDisabled) return;

    setIsSubmitting(true);
    setSubmitError(null);
    try {
      const session = await createAiSession(selectedWorkspaceId, {
        purpose: "CREATE",
        input_text: trimmed,
      });
      const vis = visibility || "PRIVATE";
      navigate(
        `/w/${selectedWorkspaceId}/ideas/new/ai/analyzing/${session.id}?visibility=${vis}`,
      );
    } catch (err) {
      if (err instanceof ApiError && err.code === "WORKSPACE_LLM_DISABLED") {
        setSubmitError("AI 기능이 현재 시스템 또는 작업공간 정책으로 비활성화되어 있습니다.");
      } else if (err instanceof ApiError && err.code === "SYSTEM_LLM_DISABLED") {
        setSubmitError("AI 기능이 현재 시스템 또는 작업공간 정책으로 비활성화되어 있습니다.");
      } else {
        setSubmitError(apiErrorMessage(err, "AI 세션을 시작하지 못했습니다."));
      }
      toast.error("AI 세션을 시작하지 못했습니다.");
    } finally {
      setIsSubmitting(false);
    }
  }

  return (
    <div className="min-h-full px-4 sm:px-8 py-8 max-w-[800px] mx-auto">
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

      {llmDisabled && (
        <div className="mb-6">
          <InlineAlert type="warning" title="AI 기능 비활성">
            AI 기능이 현재 시스템 또는 작업공간 정책으로 비활성화되어 있습니다.
          </InlineAlert>
        </div>
      )}

      {submitError && !llmDisabled && (
        <div className="mb-6">
          <InlineAlert type="error" title="요청 실패">
            {submitError}
          </InlineAlert>
        </div>
      )}

      <div className="space-y-6">
        <div className="bg-white rounded-xl border border-[rgba(0,0,0,0.07)] p-5">
          <h3 className="text-sm font-semibold text-[#111118] mb-4">기본 설정</h3>
          <div className="grid grid-cols-2 gap-4">
            <Select
              label="등록 작업공간"
              value={selectedWorkspaceId}
              onChange={(e) => handleWorkspaceChange(e.target.value)}
              options={workspaceOptions}
            />
            <Select
              label="공개 범위"
              value={visibility}
              onChange={(e) => setVisibility(e.target.value as IdeaVisibility)}
              options={[
                { value: "PRIVATE", label: "비공개" },
                { value: "WORKSPACE", label: "작업공간 공유" },
                { value: "SELECTED_USERS", label: "지정 사용자 공유" },
              ]}
            />
          </div>
          <p className="mt-2 text-xs text-[#9ca3af]">
            공개 범위는 초안 검토 후 등록 시 적용됩니다. 기본값은 비공개입니다.
          </p>
        </div>

        <div className="bg-white rounded-xl border border-[rgba(0,0,0,0.07)] p-5">
          <div className="flex items-center justify-between mb-3">
            <h3 className="text-sm font-semibold text-[#111118]">아이디어 내용</h3>
            <span className="text-xs font-mono text-[#9ca3af]">
              {text.length}/5000
            </span>
          </div>
          <textarea
            value={text}
            onChange={(e) => setText(e.target.value)}
            placeholder={`어떤 문제를 발견했는지, 누구를 위한 것인지,\n어떻게 해결하면 좋을지 자유롭게 적어보세요.\n\n완성된 문장이 아니어도 되고, 키워드만 나열해도 됩니다.`}
            className="w-full h-48 rounded-lg border border-[rgba(0,0,0,0.1)] bg-[#f8f8fb] px-4 py-3 text-sm text-[#111118] placeholder:text-[#9ca3af] resize-none focus:outline-none focus:ring-2 focus:ring-[#4f46e5]/15 focus:border-[#4f46e5] focus:bg-white transition-all"
            maxLength={5000}
            disabled={isSubmitting}
          />
        </div>

        <div className="bg-white rounded-xl border border-[rgba(0,0,0,0.07)] p-5">
          <h3 className="text-sm font-semibold text-[#111118] mb-4">AI 분석 범위</h3>
          <div className="space-y-4">
            <div className="flex gap-3">
              <Check className="w-4 h-4 text-[#16a34a] shrink-0 mt-0.5" />
              <div>
                <p className="text-sm font-medium text-[#111118]">최소 검증 방법</p>
                <p className="text-xs text-[#6b6b80] mt-0.5">AI 초안에 기본 포함됩니다.</p>
              </div>
            </div>
            <div className="flex gap-3">
              <Check className="w-4 h-4 text-[#16a34a] shrink-0 mt-0.5" />
              <div>
                <p className="text-sm font-medium text-[#111118]">위험요소 및 주요 난제</p>
                <p className="text-xs text-[#6b6b80] mt-0.5">AI 초안에 기본 포함됩니다.</p>
              </div>
            </div>
            <div className="pt-3 border-t border-[rgba(0,0,0,0.06)] space-y-3">
              <div>
                <p className="text-sm font-medium text-[#111118]">웹 조사</p>
                <p className="text-xs text-[#6b6b80] mt-0.5">
                  초안 검토 단계에서 검색어를 확인하고 사용자가 승인한 경우에만 실행할 수 있습니다.
                </p>
              </div>
              <div>
                <p className="text-sm font-medium text-[#111118]">반대 관점</p>
                <p className="text-xs text-[#6b6b80] mt-0.5">
                  {"아이디어 등록 후 AI로 발전시키기 > 반대 관점에서 사용할 수 있습니다."}
                </p>
              </div>
            </div>
          </div>
        </div>
      </div>

      <div className="flex items-center justify-between mt-8 pt-6 border-t border-[rgba(0,0,0,0.06)]">
        <Button variant="ghost" onClick={() => navigate(-1)} disabled={isSubmitting}>
          취소
        </Button>
        <Button
          variant="ai"
          icon={<Sparkles className="w-4 h-4" />}
          disabled={!text.trim() || !allowLlm || llmDisabled}
          loading={isSubmitting}
          onClick={() => void handleSubmit()}
        >
          AI로 정리하기
        </Button>
      </div>
    </div>
  );
}
