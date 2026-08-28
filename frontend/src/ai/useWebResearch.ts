import { useCallback, useEffect, useRef, useState } from "react";
import { getLatestWebResearchRun } from "../api/webResearch";
import { ApiError, apiErrorMessage } from "../api/client";
import type { WebResearchRun, WebResearchRunStatus } from "../types/api";

const DEFAULT_POLL_MS = 2000;

const IN_PROGRESS_STATUSES: WebResearchRunStatus[] = [
  "QUEUED",
  "SEARCHING",
  "REFINING",
];

export function isResearchInProgress(status: WebResearchRunStatus | null | undefined): boolean {
  return status != null && IN_PROGRESS_STATUSES.includes(status);
}

export function shouldPollResearch(status: WebResearchRunStatus | null | undefined): boolean {
  return isResearchInProgress(status);
}

export function researchRequestKey(
  workspaceId: string | undefined,
  sessionId: string | undefined,
): string | null {
  if (!workspaceId || !sessionId) return null;
  return `${workspaceId}:${sessionId}:research`;
}

export function shouldApplyResearchResponse(
  activeKey: string | null,
  requestKey: string,
  cancelled: boolean,
): boolean {
  return !cancelled && activeKey === requestKey;
}

export function useWebResearch(
  workspaceId: string | undefined,
  sessionId: string | undefined,
  options?: { pollIntervalMs?: number; enabled?: boolean },
) {
  const pollIntervalMs = options?.pollIntervalMs ?? DEFAULT_POLL_MS;
  const enabled = options?.enabled ?? true;

  const [run, setRun] = useState<WebResearchRun | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [pollError, setPollError] = useState<string | null>(null);

  const activeKeyRef = useRef<string | null>(null);
  const inFlightKeyRef = useRef<string | null>(null);
  const latestStatusRef = useRef<WebResearchRunStatus | null>(null);
  const cancelledRef = useRef(false);
  const timerRef = useRef<number | null>(null);
  const hasRunRef = useRef(false);

  const clearTimer = useCallback(() => {
    if (timerRef.current != null) {
      window.clearTimeout(timerRef.current);
      timerRef.current = null;
    }
  }, []);

  const applyRun = useCallback((next: WebResearchRun | null, requestKey: string) => {
    if (!shouldApplyResearchResponse(activeKeyRef.current, requestKey, cancelledRef.current)) {
      return;
    }
    hasRunRef.current = next != null;
    latestStatusRef.current = next?.status ?? null;
    setRun(next);
    setError(null);
    setPollError(null);
  }, []);

  const fetchOnce = useCallback(
    async (requestKey: string): Promise<WebResearchRun | null> => {
      if (!workspaceId || !sessionId || !enabled) return null;
      if (inFlightKeyRef.current === requestKey) return null;

      inFlightKeyRef.current = requestKey;
      try {
        const response = await getLatestWebResearchRun(workspaceId, sessionId);
        if (!shouldApplyResearchResponse(activeKeyRef.current, requestKey, cancelledRef.current)) {
          return null;
        }
        const next = response.run;
        applyRun(next, requestKey);
        setLoading(false);
        return next;
      } catch (err) {
        if (!shouldApplyResearchResponse(activeKeyRef.current, requestKey, cancelledRef.current)) {
          return null;
        }
        const message = apiErrorMessage(err, "웹 조사 상태를 불러오지 못했습니다.");
        if (err instanceof ApiError && err.status === 404) {
          latestStatusRef.current = null;
          setRun(null);
          hasRunRef.current = false;
          setError(message);
        } else if (hasRunRef.current || shouldPollResearch(latestStatusRef.current)) {
          setPollError(message);
        } else {
          setError(message);
        }
        setLoading(false);
        return null;
      } finally {
        if (inFlightKeyRef.current === requestKey) {
          inFlightKeyRef.current = null;
        }
      }
    },
    [workspaceId, sessionId, enabled, applyRun],
  );

  const startPollingLoop = useCallback(
    (requestKey: string) => {
      clearTimer();

      const tick = async () => {
        if (!shouldApplyResearchResponse(activeKeyRef.current, requestKey, cancelledRef.current)) {
          return;
        }
        if (!shouldPollResearch(latestStatusRef.current)) {
          return;
        }

        const next = await fetchOnce(requestKey);
        if (!shouldApplyResearchResponse(activeKeyRef.current, requestKey, cancelledRef.current)) {
          return;
        }

        if (next) {
          latestStatusRef.current = next.status;
        }

        if (shouldPollResearch(latestStatusRef.current)) {
          timerRef.current = window.setTimeout(() => {
            void tick();
          }, pollIntervalMs);
        }
      };

      timerRef.current = window.setTimeout(() => {
        void tick();
      }, pollIntervalMs);
    },
    [clearTimer, fetchOnce, pollIntervalMs],
  );

  const refresh = useCallback(async (): Promise<WebResearchRun | null> => {
    const requestKey = researchRequestKey(workspaceId, sessionId);
    if (!requestKey) return null;

    const next = await fetchOnce(requestKey);
    if (shouldApplyResearchResponse(activeKeyRef.current, requestKey, cancelledRef.current)) {
      if (shouldPollResearch(next?.status ?? latestStatusRef.current)) {
        startPollingLoop(requestKey);
      }
    }
    return next;
  }, [workspaceId, sessionId, fetchOnce, startPollingLoop]);

  useEffect(() => {
    const requestKey = researchRequestKey(workspaceId, sessionId);
    activeKeyRef.current = requestKey;
    cancelledRef.current = false;
    setLoading(true);
    setError(null);
    setPollError(null);
    setRun(null);
    hasRunRef.current = false;
    latestStatusRef.current = null;
    clearTimer();

    if (!requestKey || !enabled) {
      setLoading(false);
      return () => {
        cancelledRef.current = true;
        clearTimer();
      };
    }

    void (async () => {
      const next = await fetchOnce(requestKey);
      if (shouldApplyResearchResponse(activeKeyRef.current, requestKey, cancelledRef.current)) {
        setLoading(false);
        if (shouldPollResearch(next?.status)) {
          startPollingLoop(requestKey);
        }
      }
    })();

    return () => {
      cancelledRef.current = true;
      clearTimer();
    };
    // Re-bind only when ids / enabled change
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [workspaceId, sessionId, enabled]);

  return {
    run,
    loading,
    error,
    pollError,
    refresh,
    inProgress: isResearchInProgress(run?.status),
  };
}
