import { useCallback, useEffect, useRef, useState } from "react";
import { getLatestWebResearchRun } from "../api/webResearch";
import { apiErrorMessage } from "../api/client";
import type { WebResearchRun, WebResearchRunStatus } from "../types/api";

const DEFAULT_POLL_MS = 2000;

const ACTIVE_STATUSES: WebResearchRunStatus[] = [
  "AWAITING_APPROVAL",
  "QUEUED",
  "SEARCHING",
  "REFINING",
];

const IN_PROGRESS_STATUSES: WebResearchRunStatus[] = [
  "QUEUED",
  "SEARCHING",
  "REFINING",
];

export function isResearchInProgress(status: WebResearchRunStatus | null | undefined): boolean {
  return status != null && IN_PROGRESS_STATUSES.includes(status);
}

export function shouldPollResearch(status: WebResearchRunStatus | null | undefined): boolean {
  return status != null && ACTIVE_STATUSES.includes(status);
}

export function researchRequestKey(
  workspaceId: string | undefined,
  sessionId: string | undefined,
): string | null {
  if (!workspaceId || !sessionId) return null;
  return `${workspaceId}:${sessionId}:research`;
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

  const activeKeyRef = useRef<string | null>(null);
  const inFlightKeyRef = useRef<string | null>(null);
  const latestStatusRef = useRef<WebResearchRunStatus | null>(null);
  const cancelledRef = useRef(false);
  const timerRef = useRef<number | null>(null);

  const clearTimer = useCallback(() => {
    if (timerRef.current != null) {
      window.clearTimeout(timerRef.current);
      timerRef.current = null;
    }
  }, []);

  const fetchOnce = useCallback(
    async (requestKey: string): Promise<WebResearchRun | null> => {
      if (!workspaceId || !sessionId || !enabled) return null;
      if (inFlightKeyRef.current === requestKey) return null;

      inFlightKeyRef.current = requestKey;
      try {
        const response = await getLatestWebResearchRun(workspaceId, sessionId);
        if (cancelledRef.current || activeKeyRef.current !== requestKey) return null;
        const next = response.run;
        latestStatusRef.current = next?.status ?? null;
        setRun(next);
        setError(null);
        setLoading(false);
        return next;
      } catch (err) {
        if (cancelledRef.current || activeKeyRef.current !== requestKey) return null;
        setError(apiErrorMessage(err));
        setLoading(false);
        return null;
      } finally {
        if (inFlightKeyRef.current === requestKey) {
          inFlightKeyRef.current = null;
        }
      }
    },
    [workspaceId, sessionId, enabled],
  );

  const refresh = useCallback(async () => {
    const key = researchRequestKey(workspaceId, sessionId);
    if (!key) return null;
    return fetchOnce(key);
  }, [workspaceId, sessionId, fetchOnce]);

  useEffect(() => {
    const key = researchRequestKey(workspaceId, sessionId);
    cancelledRef.current = false;
    activeKeyRef.current = key;
    clearTimer();

    if (!key || !enabled) {
      setRun(null);
      setLoading(false);
      return () => {
        cancelledRef.current = true;
      };
    }

    setLoading(true);

    const poll = async () => {
      const next = await fetchOnce(key);
      if (cancelledRef.current || activeKeyRef.current !== key) return;
      if (shouldPollResearch(next?.status)) {
        timerRef.current = window.setTimeout(() => void poll(), pollIntervalMs);
      }
    };

    void poll();

    return () => {
      cancelledRef.current = true;
      clearTimer();
    };
  }, [workspaceId, sessionId, enabled, fetchOnce, pollIntervalMs, clearTimer]);

  return {
    run,
    loading,
    error,
    refresh,
    inProgress: isResearchInProgress(run?.status),
  };
}
