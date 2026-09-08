import { useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router";
import { clsx } from "clsx";
import { Sparkles, CheckCircle2, XCircle, Loader2, CircleHelp } from "lucide-react";
import { useAiTasks } from "../../ai/AiTasksProvider";
import { formatRelativeTime, type AiTaskViewModel } from "../../ai/aiTaskDisplay";

function StatusIcon({ task }: { task: AiTaskViewModel }) {
  if (task.isActive) {
    return <Loader2 className="w-3.5 h-3.5 text-[#4f46e5] animate-spin shrink-0" />;
  }
  if (task.status === "FAILED") {
    return <XCircle className="w-3.5 h-3.5 text-[#dc2626] shrink-0" />;
  }
  if (task.status === "NEEDS_CLARIFICATION") {
    return <CircleHelp className="w-3.5 h-3.5 text-[#d97706] shrink-0" />;
  }
  return <CheckCircle2 className="w-3.5 h-3.5 text-[#16a34a] shrink-0" />;
}

export function AiTasksIndicator() {
  const navigate = useNavigate();
  const { tasks, activeCount, loading } = useAiTasks();
  const [open, setOpen] = useState(false);
  const rootRef = useRef<HTMLDivElement>(null);

  const recentTerminalCount = tasks.filter((t) => !t.isActive && t.status === "FAILED").length;
  const showDot = activeCount > 0 || recentTerminalCount > 0;

  useEffect(() => {
    if (!open) return;
    function onPointerDown(event: MouseEvent) {
      if (!rootRef.current?.contains(event.target as Node)) {
        setOpen(false);
      }
    }
    function onKeyDown(event: KeyboardEvent) {
      if (event.key === "Escape") setOpen(false);
    }
    document.addEventListener("mousedown", onPointerDown);
    document.addEventListener("keydown", onKeyDown);
    return () => {
      document.removeEventListener("mousedown", onPointerDown);
      document.removeEventListener("keydown", onKeyDown);
    };
  }, [open]);

  return (
    <div ref={rootRef} className="relative">
      <button
        type="button"
        aria-label="AI 작업 상태"
        aria-expanded={open}
        onClick={() => setOpen((v) => !v)}
        className={clsx(
          "h-8 px-2 flex items-center gap-1.5 rounded-lg text-[#6b6b80] hover:bg-[#f4f4f8] relative transition-colors",
          open && "bg-[#f4f4f8] text-[#111118]",
          activeCount > 0 && "text-[#4f46e5]",
        )}
      >
        <Sparkles className="w-4 h-4" />
        <span className="hidden sm:inline text-xs font-medium">
          {activeCount > 0 ? `AI 작업 ${activeCount}` : "AI 작업"}
        </span>
        {showDot && (
          <span
            className={clsx(
              "absolute top-1 right-1 w-2 h-2 rounded-full",
              activeCount > 0 ? "bg-[#4f46e5]" : "bg-[#dc2626]",
            )}
          />
        )}
      </button>

      {open && (
        <div className="absolute top-full right-0 mt-1 w-80 bg-white rounded-xl border border-[rgba(0,0,0,0.08)] shadow-lg z-50">
          <div className="flex items-center justify-between px-4 py-3 border-b border-[rgba(0,0,0,0.06)]">
            <p className="text-sm font-semibold text-[#111118]">AI 작업</p>
            {activeCount > 0 && (
              <span className="text-[11px] font-medium text-[#4f46e5] bg-[#eef2ff] px-2 py-0.5 rounded-full">
                진행 중 {activeCount}
              </span>
            )}
          </div>
          <div className="max-h-80 overflow-y-auto">
            {loading && tasks.length === 0 ? (
              <p className="px-4 py-6 text-sm text-[#6b6b80]">불러오는 중...</p>
            ) : tasks.length === 0 ? (
              <p className="px-4 py-6 text-sm text-[#6b6b80]">진행 중인 AI 작업이 없습니다.</p>
            ) : (
              tasks.map((task) => (
                <button
                  key={task.id}
                  type="button"
                  className="w-full text-left px-4 py-3 border-b border-[rgba(0,0,0,0.04)] hover:bg-[#f8f8fb] transition-colors"
                  onClick={() => {
                    if (task.href) {
                      navigate(task.href);
                      setOpen(false);
                    }
                  }}
                  disabled={!task.href}
                >
                  <div className="flex items-start gap-2.5">
                    <StatusIcon task={task} />
                    <div className="min-w-0 flex-1">
                      <p className="text-sm font-medium text-[#111118] truncate">
                        {task.ideaTitle}
                      </p>
                      <p className="text-xs text-[#6b6b80] mt-0.5">
                        {task.typeLabel} · {task.displayStatus}
                      </p>
                      {(task.startedAt || task.completedAt) && (
                        <p className="text-[11px] text-[#9ca3af] mt-1">
                          {formatRelativeTime(task.completedAt || task.startedAt)}
                        </p>
                      )}
                      {!task.isActive && task.href && (
                        <p className="text-[11px] text-[#4f46e5] mt-1">결과 보기</p>
                      )}
                    </div>
                  </div>
                </button>
              ))
            )}
          </div>
        </div>
      )}
    </div>
  );
}
