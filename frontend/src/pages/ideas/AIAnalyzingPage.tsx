import { useEffect, useMemo, useState } from "react";
import { useNavigate, useParams, useSearchParams } from "react-router";
import { clsx } from "clsx";
import {
  Sparkles,
  Check,
  Loader2,
  AlertCircle,
  RefreshCw,
  ChevronRight,
} from "lucide-react";
import { Button } from "../../components/common/Button";
import { ProgressStepper, InlineAlert } from "../../components/common/EmptyState";
import { toast } from "../../components/common/Toast";
import {
  retryAiSession,
  submitAiClarifications,
} from "../../api/aiSessions";
import { ApiError, apiErrorMessage } from "../../api/client";
import {
  formatElapsedSince,
  parseVisibilityParam,
  useAiSession,
} from "../../ai/useAiSession";
import type { AiSessionStatus } from "../../types/api";

type StepStatus = "waiting" | "running" | "done" | "failed" | "paused";

interface Step {
  id: string;
  label: string;
  status: StepStatus;
}

const STEP_ICONS: Record<StepStatus, React.ReactNode> = {
  waiting: <span className="w-2 h-2 rounded-full bg-[#e8e8f0] block" />,
  running: <Loader2 className="w-3.5 h-3.5 text-[#4f46e5] animate-spin" />,
  done: <Check className="w-3.5 h-3.5 text-[#16a34a]" />,
  failed: <AlertCircle className="w-3.5 h-3.5 text-[#dc2626]" />,
  paused: <span className="w-2 h-2 rounded-full bg-[#f59e0b] block" />,
};

function buildSteps(status: AiSessionStatus | undefined): Step[] {
  const base: Step[] = [
    { id: "accepted", label: "AI 요청 접수", status: "waiting" },
    { id: "structure", label: "AI 구조화 처리", status: "waiting" },
    { id: "draft", label: "등록 초안 준비", status: "waiting" },
  ];

  if (!status || status === "PROCESSING") {
    return [
      { ...base[0], status: "done" },
      { ...base[1], status: "running" },
      { ...base[2], status: "waiting" },
    ];
  }
  if (status === "NEEDS_CLARIFICATION") {
    return [
      { ...base[0], status: "done" },
      { ...base[1], status: "paused" },
      { ...base[2], status: "waiting" },
    ];
  }
  if (status === "READY_FOR_REVIEW" || status === "CONFIRMED") {
    return base.map((s) => ({ ...s, status: "done" as const }));
  }
  if (status === "FAILED") {
    return [
      { ...base[0], status: "done" },
      { ...base[1], status: "failed" },
      { ...base[2], status: "waiting" },
    ];
  }
  if (status === "CANCELLED") {
    return [
      { ...base[0], status: "done" },
      { ...base[1], status: "failed" },
      { ...base[2], status: "waiting" },
    ];
  }
  return base;
}

export function AIAnalyzingPage() {
  const navigate = useNavigate();
  const { workspaceId = "", sessionId = "" } = useParams();
  const [searchParams] = useSearchParams();
  const visibility = parseVisibilityParam(searchParams.get("visibility"));

  const { session, setSession, loading, error, pollError, refresh, clearPollError } =
    useAiSession(workspaceId, sessionId);

  const [answers, setAnswers] = useState<Record<string, string>>({});
  const [isSubmittingClarification, setIsSubmittingClarification] = useState(false);
  const [isRetrying, setIsRetrying] = useState(false);
  const [actionError, setActionError] = useState<string | null>(null);
  const [, setTick] = useState(0);

  useEffect(() => {
    const t = window.setInterval(() => setTick((n) => n + 1), 1000);
    return () => window.clearInterval(t);
  }, []);

  // Redirect when already confirmed
  useEffect(() => {
    if (!session || !workspaceId) return;
    if (session.status === "CONFIRMED" && session.result_idea_id) {
      navigate(`/w/${workspaceId}/ideas/${session.result_idea_id}`, {
        replace: true,
      });
    }
  }, [session, workspaceId, navigate]);

  // Reset answer drafts when questions change
  useEffect(() => {
    if (session?.status !== "NEEDS_CLARIFICATION") {
      setAnswers({});
      return;
    }
    const qs = session.clarifying_questions ?? [];
    setAnswers((prev) => {
      const next: Record<string, string> = {};
      for (const q of qs) {
        next[q.id] = prev[q.id] ?? "";
      }
      return next;
    });
  }, [session?.status, session?.clarifying_questions]);

  const steps = useMemo(() => buildSteps(session?.status), [session?.status]);

  const statusLabel: Record<StepStatus, string> = {
    waiting: "대기",
    running: "진행 중",
    done: "완료",
    failed: "실패",
    paused: "일시 중지",
  };

  const modelLabel = session?.llm?.model?.trim()
    ? session.llm.model
    : session?.status === "PROCESSING"
      ? "처리 중"
      : "AI 모델";

  const elapsed = formatElapsedSince(session?.created_at);
  const startedAt = session?.created_at
    ? new Date(session.created_at).toLocaleTimeString("ko", {
        hour: "2-digit",
        minute: "2-digit",
      })
    : "—";

  const questions = session?.clarifying_questions ?? [];
  const canSubmitClarification =
    questions.length > 0 &&
    questions.every((q) => (answers[q.id] ?? "").trim().length > 0);

  async function handleClarificationSubmit() {
    if (!workspaceId || !sessionId || !canSubmitClarification || isSubmittingClarification) {
      return;
    }
    setIsSubmittingClarification(true);
    setActionError(null);
    try {
      const updated = await submitAiClarifications(workspaceId, sessionId, {
        answers: questions.map((q) => ({
          question_id: q.id,
          answer: answers[q.id].trim(),
        })),
      });
      setSession(updated);
    } catch (err) {
      if (err instanceof ApiError && err.status === 409) {
        await refresh();
        setActionError("세션 상태가 변경되었습니다. 다시 확인합니다.");
      } else {
        setActionError(apiErrorMessage(err, "답변을 제출하지 못했습니다."));
      }
    } finally {
      setIsSubmittingClarification(false);
    }
  }

  async function handleRetry() {
    if (!workspaceId || !sessionId || isRetrying) return;
    setIsRetrying(true);
    setActionError(null);
    try {
      const updated = await retryAiSession(workspaceId, sessionId);
      setSession(updated);
    } catch (err) {
      if (err instanceof ApiError && err.status === 409) {
        await refresh();
        setActionError("세션 상태가 변경되었습니다. 다시 확인합니다.");
      } else {
        setActionError(apiErrorMessage(err, "다시 시도하지 못했습니다."));
        toast.error("다시 시도하지 못했습니다.");
      }
    } finally {
      setIsRetrying(false);
    }
  }

  function goToReview() {
    navigate(
      `/w/${workspaceId}/ideas/new/ai/review/${sessionId}?visibility=${visibility}`,
    );
  }

  if (loading) {
    return (
      <div className="min-h-full flex items-center justify-center px-4 py-12">
        <div className="flex items-center gap-2 text-sm text-[#6b6b80]">
          <Loader2 className="w-4 h-4 animate-spin" />
          AI 작업 상태를 불러오는 중...
        </div>
      </div>
    );
  }

  if (error || !session) {
    return (
      <div className="min-h-full flex items-center justify-center px-4 py-12">
        <div className="w-full max-w-lg space-y-4">
          <InlineAlert type="warning" title="AI 작업을 불러올 수 없습니다">
            {error ?? "존재하지 않거나 접근할 수 없는 AI 작업입니다."}
          </InlineAlert>
          <div className="flex gap-2">
            <Button variant="secondary" onClick={() => void refresh()}>
              다시 확인
            </Button>
            <Button
              variant="primary"
              onClick={() => navigate(`/w/${workspaceId}/ideas/new/ai`)}
            >
              새 AI 작업 시작
            </Button>
          </div>
        </div>
      </div>
    );
  }

  if (session.status === "CANCELLED") {
    return (
      <div className="min-h-full flex items-center justify-center px-4 py-12">
        <div className="w-full max-w-lg space-y-4">
          <InlineAlert type="warning" title="취소된 AI 작업">
            이 AI 작업은 취소되었습니다.
          </InlineAlert>
          <Button
            variant="primary"
            onClick={() => navigate(`/w/${workspaceId}/ideas/new/ai`)}
          >
            새 Session 시작
          </Button>
        </div>
      </div>
    );
  }

  const showClarification = session.status === "NEEDS_CLARIFICATION";
  const showFailed = session.status === "FAILED";
  const showReady = session.status === "READY_FOR_REVIEW";
  const showProcessing = session.status === "PROCESSING";

  return (
    <div className="min-h-full flex items-center justify-center px-4 py-12">
      <div className="w-full max-w-lg">
        <div className="mb-8 flex justify-center">
          <ProgressStepper
            steps={["아이디어 입력", "AI 분석", "초안 검토", "등록 완료"]}
            current={1}
          />
        </div>

        <div className="bg-white rounded-2xl border border-[rgba(0,0,0,0.07)] shadow-sm overflow-hidden">
          <div className="bg-gradient-to-r from-[#4f46e5] to-[#7c3aed] px-6 py-5">
            <div className="flex items-center gap-2.5 mb-1">
              <Sparkles className="w-5 h-5 text-white" />
              <h2 className="text-base font-bold text-white">
                {showReady
                  ? "분석이 완료되었습니다"
                  : showFailed
                    ? "분석에 실패했습니다"
                    : showClarification
                      ? "추가 정보가 필요합니다"
                      : "아이디어를 정리하고 있습니다"}
              </h2>
            </div>
            <p className="text-sm text-white/70">
              분석 중에도 다른 화면으로 이동할 수 있습니다. 이 페이지를 새로고침해도
              작업이 이어집니다.
            </p>
          </div>

          <div className="flex items-center gap-6 px-6 py-3 bg-[#f8f8fb] border-b border-[rgba(0,0,0,0.05)] text-xs text-[#6b6b80] flex-wrap">
            <span>시작 {startedAt}</span>
            <span>
              경과 {elapsed}
            </span>
            <span>
              모델: <span className="font-mono text-[#111118]">{modelLabel}</span>
            </span>
            <span>웹 검색: 미포함</span>
          </div>

          <div className="px-6 py-5 space-y-3">
            {steps.map((step) => (
              <div
                key={step.id}
                className={clsx(
                  "flex items-center gap-3 py-2 px-3 rounded-lg transition-colors",
                  step.status === "running" && "bg-[#f5f3ff]",
                  step.status === "done" && "bg-[#f0fdf4]",
                  step.status === "failed" && "bg-[#fef2f2]",
                  step.status === "paused" && "bg-[#fffbeb]",
                )}
              >
                <div className="w-5 h-5 flex items-center justify-center shrink-0">
                  {STEP_ICONS[step.status]}
                </div>
                <span
                  className={clsx(
                    "text-sm flex-1",
                    step.status === "done" && "text-[#15803d]",
                    step.status === "running" && "text-[#4f46e5] font-medium",
                    step.status === "waiting" && "text-[#9ca3af]",
                    step.status === "failed" && "text-[#dc2626]",
                    step.status === "paused" && "text-[#b45309]",
                  )}
                >
                  {step.label}
                </span>
                <span
                  className={clsx(
                    "text-xs",
                    step.status === "running" && "text-[#4f46e5]",
                    step.status === "done" && "text-[#16a34a]",
                    step.status === "waiting" && "text-[#d1d5db]",
                    step.status === "failed" && "text-[#dc2626]",
                    step.status === "paused" && "text-[#b45309]",
                  )}
                >
                  {statusLabel[step.status]}
                </span>
              </div>
            ))}
          </div>

          {pollError && (
            <div className="mx-6 mb-4">
              <InlineAlert type="warning" title="상태를 확인하지 못했습니다.">
                {pollError}
              </InlineAlert>
              <Button
                variant="secondary"
                size="sm"
                className="mt-2"
                onClick={() => {
                  clearPollError();
                  void refresh();
                }}
              >
                다시 확인
              </Button>
            </div>
          )}

          {actionError && (
            <div className="mx-6 mb-4">
              <InlineAlert type="warning" title="요청 처리 실패">
                {actionError}
              </InlineAlert>
            </div>
          )}

          {showClarification && (
            <div className="mx-6 mb-5 rounded-xl border border-[#ddd6fe] bg-[#f5f3ff] p-4">
              <p className="text-sm font-semibold text-[#4f46e5] mb-3">
                조금만 더 알려주시면 더 정확히 정리할 수 있습니다
              </p>
              <div className="space-y-4">
                {questions.map((q) => (
                  <div key={q.id}>
                    <p className="text-sm text-[#111118] mb-2">{q.question}</p>
                    <textarea
                      value={answers[q.id] ?? ""}
                      onChange={(e) =>
                        setAnswers((prev) => ({
                          ...prev,
                          [q.id]: e.target.value,
                        }))
                      }
                      rows={2}
                      className="w-full rounded-lg border border-[#c4b5fd] bg-white px-3 py-2 text-sm text-[#111118] resize-none focus:outline-none focus:ring-2 focus:ring-[#4f46e5]/20"
                      placeholder="답변을 입력하세요"
                      disabled={isSubmittingClarification}
                    />
                  </div>
                ))}
              </div>
              <div className="flex gap-2 mt-3">
                <Button
                  variant="primary"
                  size="sm"
                  loading={isSubmittingClarification}
                  disabled={!canSubmitClarification}
                  onClick={() => void handleClarificationSubmit()}
                >
                  답변 제출
                </Button>
              </div>
            </div>
          )}

          {showFailed && (
            <div className="px-6 pb-6">
              <div className="rounded-xl bg-[#fef2f2] border border-[#fecaca] p-4 mb-4">
                <div className="flex items-start gap-2">
                  <AlertCircle className="w-4 h-4 text-[#dc2626] mt-0.5 shrink-0" />
                  <div>
                    <p className="text-sm font-semibold text-[#b91c1c]">
                      {session.failure?.message || "AI 분석에 실패했습니다."}
                    </p>
                    {session.failure?.code && (
                      <p className="text-xs text-[#9ca3af] mt-1 font-mono">
                        {session.failure.code}
                      </p>
                    )}
                  </div>
                </div>
              </div>
              <Button
                variant="primary"
                className="w-full"
                icon={<RefreshCw className="w-4 h-4" />}
                loading={isRetrying}
                onClick={() => void handleRetry()}
              >
                다시 시도
              </Button>
            </div>
          )}

          {showReady && (
            <div className="px-6 pb-6">
              <div className="rounded-xl bg-[#f0fdf4] border border-[#bbf7d0] p-4 mb-4">
                <div className="flex items-center gap-2">
                  <Check className="w-4 h-4 text-[#16a34a]" />
                  <p className="text-sm font-semibold text-[#15803d]">
                    분석 완료! 등록 초안이 준비되었습니다.
                  </p>
                </div>
              </div>
              <Button
                variant="primary"
                className="w-full"
                icon={<ChevronRight className="w-4 h-4" />}
                onClick={goToReview}
              >
                초안 검토하기
              </Button>
            </div>
          )}
        </div>

        {showProcessing && (
          <p className="text-center text-xs text-[#9ca3af] mt-4">
            분석은 보통 수십 초 정도 걸릴 수 있습니다.
          </p>
        )}
      </div>
    </div>
  );
}
