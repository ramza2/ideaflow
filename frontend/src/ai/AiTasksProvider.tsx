import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
  type ReactNode,
} from "react";
import { useNavigate } from "react-router";
import { toast as sonnerToast } from "sonner";
import { Check, AlertCircle } from "lucide-react";
import { listAiTasks } from "../api/aiTasks";
import {
  completionToastCopy,
  failureToastCopy,
  isTerminalAiTaskStatus,
  shouldEmitAiTaskCompletionToast,
  toAiTaskViewModel,
  type AiTaskViewModel,
} from "./aiTaskDisplay";
import type { AiTask } from "../types/api";

const DEFAULT_POLL_MS = 4000;

type AiTasksContextValue = {
  tasks: AiTaskViewModel[];
  activeCount: number;
  loading: boolean;
  refresh: () => Promise<void>;
};

const AiTasksContext = createContext<AiTasksContextValue | null>(null);

function notifyTaskTransition(task: AiTask, href: string | null, navigate: (to: string) => void) {
  const action =
    href != null
      ? {
          label: "결과 보기",
          onClick: () => navigate(href),
        }
      : undefined;

  if (task.status === "FAILED") {
    const copy = failureToastCopy(task);
    sonnerToast(copy.title, {
      description: copy.description,
      icon: <AlertCircle className="w-4 h-4 text-[#dc2626]" />,
      action,
    });
    return;
  }

  if (!shouldEmitAiTaskCompletionToast(task)) {
    return;
  }

  const copy = completionToastCopy(task);
  sonnerToast(copy.title, {
    description: copy.description,
    icon: <Check className="w-4 h-4 text-[#16a34a]" />,
    action,
  });
}

export function AiTasksProvider({
  workspaceId,
  children,
  pollIntervalMs = DEFAULT_POLL_MS,
}: {
  workspaceId: string;
  children: ReactNode;
  pollIntervalMs?: number;
}) {
  const navigate = useNavigate();
  const [rawTasks, setRawTasks] = useState<AiTask[]>([]);
  const [activeCount, setActiveCount] = useState(0);
  const [loading, setLoading] = useState(Boolean(workspaceId));

  const workspaceIdRef = useRef(workspaceId);
  const timerRef = useRef<number | null>(null);
  const inFlightRef = useRef(false);
  const baselineDoneRef = useRef(false);
  const prevActiveIdsRef = useRef<Set<string>>(new Set());
  const notifiedIdsRef = useRef<Set<string>>(new Set());

  const clearTimer = useCallback(() => {
    if (timerRef.current != null) {
      window.clearTimeout(timerRef.current);
      timerRef.current = null;
    }
  }, []);

  const scheduleNext = useCallback(
    (delayMs: number, tick: () => void) => {
      clearTimer();
      timerRef.current = window.setTimeout(tick, delayMs);
    },
    [clearTimer],
  );

  const fetchTasks = useCallback(async () => {
    const requestWorkspaceId = workspaceIdRef.current;
    if (!requestWorkspaceId || inFlightRef.current) return;

    inFlightRef.current = true;
    try {
      const data = await listAiTasks(requestWorkspaceId);
      if (workspaceIdRef.current !== requestWorkspaceId) return;

      const items = data.items ?? [];
      setRawTasks(items);
      setActiveCount(data.active_count ?? items.filter((t) => t.is_active).length);
      setLoading(false);

      if (!baselineDoneRef.current) {
        const activeIds = new Set<string>();
        for (const task of items) {
          if (task.is_active) {
            activeIds.add(task.id);
          } else if (isTerminalAiTaskStatus(task)) {
            // F5 / first load: do not re-toast already finished work.
            notifiedIdsRef.current.add(task.id);
          }
        }
        prevActiveIdsRef.current = activeIds;
        baselineDoneRef.current = true;
        return;
      }

      const nextActive = new Set<string>();
      for (const task of items) {
        if (task.is_active) {
          nextActive.add(task.id);
          continue;
        }
        if (!isTerminalAiTaskStatus(task)) continue;
        if (
          prevActiveIdsRef.current.has(task.id) &&
          !notifiedIdsRef.current.has(task.id)
        ) {
          const href = toAiTaskViewModel(requestWorkspaceId, task).href;
          notifyTaskTransition(task, href, navigate);
          notifiedIdsRef.current.add(task.id);
        } else {
          notifiedIdsRef.current.add(task.id);
        }
      }
      prevActiveIdsRef.current = nextActive;
    } catch {
      if (workspaceIdRef.current !== requestWorkspaceId) return;
      setLoading(false);
    } finally {
      inFlightRef.current = false;
    }
  }, [navigate]);

  const refresh = useCallback(async () => {
    await fetchTasks();
  }, [fetchTasks]);

  useEffect(() => {
    workspaceIdRef.current = workspaceId;
    baselineDoneRef.current = false;
    prevActiveIdsRef.current = new Set();
    notifiedIdsRef.current = new Set();
    setRawTasks([]);
    setActiveCount(0);
    setLoading(Boolean(workspaceId));
    clearTimer();

    if (!workspaceId) {
      setLoading(false);
      return;
    }

    let cancelled = false;

    const tick = () => {
      if (cancelled) return;
      if (typeof document !== "undefined" && document.visibilityState === "hidden") {
        scheduleNext(pollIntervalMs, tick);
        return;
      }
      void fetchTasks().finally(() => {
        if (!cancelled) {
          scheduleNext(pollIntervalMs, tick);
        }
      });
    };

    void fetchTasks().finally(() => {
      if (!cancelled) {
        scheduleNext(pollIntervalMs, tick);
      }
    });

    const onVisibility = () => {
      if (document.visibilityState === "visible") {
        void fetchTasks();
      }
    };
    document.addEventListener("visibilitychange", onVisibility);

    return () => {
      cancelled = true;
      clearTimer();
      document.removeEventListener("visibilitychange", onVisibility);
    };
  }, [workspaceId, pollIntervalMs, fetchTasks, clearTimer, scheduleNext]);

  const tasks = useMemo(
    () => rawTasks.map((task) => toAiTaskViewModel(workspaceId, task)),
    [rawTasks, workspaceId],
  );

  const value = useMemo<AiTasksContextValue>(
    () => ({
      tasks,
      activeCount,
      loading,
      refresh,
    }),
    [tasks, activeCount, loading, refresh],
  );

  return <AiTasksContext.Provider value={value}>{children}</AiTasksContext.Provider>;
}

export function useAiTasks(): AiTasksContextValue {
  const ctx = useContext(AiTasksContext);
  if (!ctx) {
    return {
      tasks: [],
      activeCount: 0,
      loading: false,
      refresh: async () => undefined,
    };
  }
  return ctx;
}
