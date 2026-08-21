import { useState, useEffect } from "react";
import { useNavigate, useParams } from "react-router";
import { clsx } from "clsx";
import {
  Sparkles,
  Check,
  Loader2,
  AlertCircle,
  SkipForward,
  RefreshCw,
  ChevronRight,
} from "lucide-react";
import { Button } from "../../components/common/Button";
import { ProgressStepper } from "../../components/common/EmptyState";
import { WebSearchApprovalPanel } from "../../components/ai/WebSearchApprovalPanel";

type StepStatus = "waiting" | "running" | "done" | "failed" | "skipped";

interface Step {
  id: string;
  label: string;
  status: StepStatus;
}

const INITIAL_STEPS: Step[] = [
  { id: "understand", label: "입력 내용 이해", status: "waiting" },
  { id: "extract", label: "핵심 문제와 목표 추출", status: "waiting" },
  { id: "structure", label: "구조화된 항목 생성", status: "waiting" },
  { id: "similar", label: "유사 아이디어 확인", status: "waiting" },
  { id: "webcheck", label: "외부 정보 필요 여부 판단", status: "waiting" },
  { id: "draft", label: "등록 초안 준비", status: "waiting" },
];

const STEP_ICONS: Record<StepStatus, React.ReactNode> = {
  waiting: <span className="w-2 h-2 rounded-full bg-[#e8e8f0] block" />,
  running: <Loader2 className="w-3.5 h-3.5 text-[#4f46e5] animate-spin" />,
  done: <Check className="w-3.5 h-3.5 text-[#16a34a]" />,
  failed: <AlertCircle className="w-3.5 h-3.5 text-[#dc2626]" />,
  skipped: <SkipForward className="w-3.5 h-3.5 text-[#9ca3af]" />,
};

export function AIAnalyzingPage() {
  const navigate = useNavigate();
  const { workspaceId = "personal" } = useParams();
  const [steps, setSteps] = useState<Step[]>(INITIAL_STEPS);
  const [currentStep, setCurrentStep] = useState(0);
  const [elapsed, setElapsed] = useState(0);
  const [done, setDone] = useState(false);
  const [showQuestion, setShowQuestion] = useState(false);
  const [showWebSearch, setShowWebSearch] = useState(false);

  useEffect(() => {
    const timer = setInterval(() => setElapsed((e) => e + 1), 1000);
    return () => clearInterval(timer);
  }, []);

  useEffect(() => {
    if (currentStep >= INITIAL_STEPS.length) {
      setDone(true);
      return;
    }

    setSteps((prev) =>
      prev.map((s, i) =>
        i === currentStep ? { ...s, status: "running" } : s
      )
    );

    const delay = currentStep === 3 ? 1500 : 900;
    const t = setTimeout(() => {
      setSteps((prev) =>
        prev.map((s, i) =>
          i === currentStep ? { ...s, status: "done" } : s
        )
      );

      if (currentStep === 2) {
        setTimeout(() => setShowQuestion(true), 300);
      }
      if (currentStep === 4) {
        setTimeout(() => setShowWebSearch(true), 400);
      }

      setCurrentStep((c) => c + 1);
    }, delay);

    return () => clearTimeout(t);
  }, [currentStep]);

  const statusLabel: Record<StepStatus, string> = {
    waiting: "대기",
    running: "진행 중",
    done: "완료",
    failed: "실패",
    skipped: "건너뜀",
  };

  return (
    <div className="min-h-full flex items-center justify-center px-4 py-12">
      <div className="w-full max-w-lg">
        {/* Stepper */}
        <div className="mb-8 flex justify-center">
          <ProgressStepper
            steps={["아이디어 입력", "AI 분석", "초안 검토", "등록 완료"]}
            current={1}
          />
        </div>

        <div className="bg-white rounded-2xl border border-[rgba(0,0,0,0.07)] shadow-sm overflow-hidden">
          {/* Header */}
          <div className="bg-gradient-to-r from-[#4f46e5] to-[#7c3aed] px-6 py-5">
            <div className="flex items-center gap-2.5 mb-1">
              <Sparkles className="w-5 h-5 text-white" />
              <h2 className="text-base font-bold text-white">아이디어를 정리하고 있습니다</h2>
            </div>
            <p className="text-sm text-white/70">분석 중에도 다른 화면으로 이동할 수 있습니다. 완료되면 알림으로 알려드립니다.</p>
          </div>

          {/* Meta */}
          <div className="flex items-center gap-6 px-6 py-3 bg-[#f8f8fb] border-b border-[rgba(0,0,0,0.05)] text-xs text-[#6b6b80]">
            <span>시작 {new Date().toLocaleTimeString("ko", { hour: "2-digit", minute: "2-digit" })}</span>
            <span>경과 {Math.floor(elapsed / 60)}:{String(elapsed % 60).padStart(2, "0")}</span>
            <span>모델: <span className="font-mono text-[#111118]">Qwen3-14B</span></span>
            <span>웹 검색: 미포함</span>
          </div>

          {/* Steps */}
          <div className="px-6 py-5 space-y-3">
            {steps.map((step, i) => (
              <div
                key={step.id}
                className={clsx(
                  "flex items-center gap-3 py-2 px-3 rounded-lg transition-colors",
                  step.status === "running" && "bg-[#f5f3ff]",
                  step.status === "done" && "bg-[#f0fdf4]",
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
                    step.status === "skipped" && "text-[#9ca3af] line-through",
                  )}
                >
                  {step.label}
                </span>
                <span className={clsx(
                  "text-xs",
                  step.status === "running" && "text-[#4f46e5]",
                  step.status === "done" && "text-[#16a34a]",
                  step.status === "waiting" && "text-[#d1d5db]",
                )}>
                  {statusLabel[step.status]}
                </span>
              </div>
            ))}
          </div>

          {/* Question panel */}
          {showQuestion && !done && (
            <div className="mx-6 mb-5 rounded-xl border border-[#ddd6fe] bg-[#f5f3ff] p-4">
              <p className="text-sm font-semibold text-[#4f46e5] mb-3">
                조금만 더 알려주시면 더 정확히 정리할 수 있습니다
              </p>
              <div className="space-y-3">
                <div>
                  <p className="text-sm text-[#111118] mb-2">주 사용자는 누구인가요?</p>
                  <div className="flex flex-wrap gap-2">
                    {["개인 개발자", "기업 팀", "연구자", "스타트업"].map((opt) => (
                      <button
                        key={opt}
                        className="px-3 py-1.5 text-xs rounded-full border border-[#c4b5fd] text-[#7c3aed] hover:bg-[#ede9fe] transition-colors"
                      >
                        {opt}
                      </button>
                    ))}
                  </div>
                </div>
              </div>
              <div className="flex gap-2 mt-3">
                <button className="text-xs text-[#6b6b80] hover:text-[#4f46e5]">건너뛰기</button>
                <button className="text-xs text-[#6b6b80] hover:text-[#4f46e5]">AI가 합리적으로 가정</button>
              </div>
            </div>
          )}

          {/* Done state */}
          {done && (
            <div className="px-6 pb-6">
              <div className="rounded-xl bg-[#f0fdf4] border border-[#bbf7d0] p-4 mb-4">
                <div className="flex items-center gap-2">
                  <Check className="w-4.5 h-4.5 text-[#16a34a]" />
                  <p className="text-sm font-semibold text-[#15803d]">분석 완료! 등록 초안이 준비되었습니다.</p>
                </div>
              </div>
              <Button
                variant="primary"
                className="w-full"
                icon={<ChevronRight className="w-4 h-4" />}
                onClick={() => navigate(`/w/${workspaceId}/ideas/new/ai/review`)}
              >
                초안 검토하기
              </Button>
            </div>
          )}
        </div>

        {!done && (
          <p className="text-center text-xs text-[#9ca3af] mt-4">
            분석은 보통 15~30초 걸립니다.
          </p>
        )}
      </div>

      <WebSearchApprovalPanel
        open={showWebSearch}
        onClose={() => setShowWebSearch(false)}
        onApprove={() => { setShowWebSearch(false); }}
        onSkip={() => setShowWebSearch(false)}
      />
    </div>
  );
}
