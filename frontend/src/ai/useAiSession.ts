import { useCallback, useEffect, useRef, useState } from "react";
import { getAiSession } from "../api/aiSessions";
import { apiErrorMessage, ApiError } from "../api/client";
import type { AiSession, AiSessionStatus, IdeaVisibility } from "../types/api";
import type { SourceBadgeType } from "../types";

const DEFAULT_POLL_MS = 1800;

export function sessionRequestKey(
  workspaceId: string | undefined,
  sessionId: string | undefined,
): string | null {
  if (!workspaceId || !sessionId) return null;
  return `${workspaceId}:${sessionId}`;
}

export function shouldApplySessionResponse(
  activeKey: string | null,
  requestKey: string,
  cancelled: boolean,
): boolean {
  return !cancelled && activeKey === requestKey;
}

export function shouldContinuePolling(status: AiSessionStatus | null): boolean {
  return status === "PROCESSING";
}

export function useAiSession(
  workspaceId: string | undefined,
  sessionId: string | undefined,
  options?: { pollWhenProcessing?: boolean; pollIntervalMs?: number },
) {
  const pollWhenProcessing = options?.pollWhenProcessing ?? true;
  const pollIntervalMs = options?.pollIntervalMs ?? DEFAULT_POLL_MS;

  const [session, setSession] = useState<AiSession | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [pollError, setPollError] = useState<string | null>(null);

  const activeKeyRef = useRef<string | null>(null);
  const inFlightKeyRef = useRef<string | null>(null);
  const latestStatusRef = useRef<AiSessionStatus | null>(null);
  const cancelledRef = useRef(false);
  const timerRef = useRef<number | null>(null);
  const hasSessionRef = useRef(false);

  const clearTimer = useCallback(() => {
    if (timerRef.current != null) {
      window.clearTimeout(timerRef.current);
      timerRef.current = null;
    }
  }, []);

  const applySession = useCallback((next: AiSession, requestKey: string) => {
    if (!shouldApplySessionResponse(activeKeyRef.current, requestKey, cancelledRef.current)) {
      return;
    }
    hasSessionRef.current = true;
    latestStatusRef.current = next.status;
    setSession(next);
    setError(null);
    setPollError(null);
  }, []);

  const fetchOnce = useCallback(
    async (requestKey: string): Promise<AiSession | null> => {
      if (!workspaceId || !sessionId) return null;
      if (inFlightKeyRef.current === requestKey) return null;

      inFlightKeyRef.current = requestKey;
      try {
        const next = await getAiSession(workspaceId, sessionId);
        if (!shouldApplySessionResponse(activeKeyRef.current, requestKey, cancelledRef.current)) {
          return null;
        }
        applySession(next, requestKey);
        return next;
      } catch (err) {
        if (!shouldApplySessionResponse(activeKeyRef.current, requestKey, cancelledRef.current)) {
          return null;
        }
        const message = apiErrorMessage(err, "AI 세션을 불러오지 못했습니다.");
        if (err instanceof ApiError && err.status === 404) {
          latestStatusRef.current = null;
          setError(
            err.code === "AI_SESSION_NOT_FOUND"
              ? "존재하지 않거나 접근할 수 없는 AI 작업입니다."
              : message,
          );
          setSession(null);
          hasSessionRef.current = false;
        } else if (hasSessionRef.current) {
          setPollError(message);
        } else {
          setError(message);
        }
        return null;
      } finally {
        if (inFlightKeyRef.current === requestKey) {
          inFlightKeyRef.current = null;
        }
      }
    },
    [workspaceId, sessionId, applySession],
  );

  const startPollingLoop = useCallback(
    (requestKey: string) => {
      if (!pollWhenProcessing) return;
      clearTimer();

      const tick = async () => {
        if (!shouldApplySessionResponse(activeKeyRef.current, requestKey, cancelledRef.current)) {
          return;
        }
        if (!shouldContinuePolling(latestStatusRef.current)) {
          return;
        }

        const next = await fetchOnce(requestKey);
        if (!shouldApplySessionResponse(activeKeyRef.current, requestKey, cancelledRef.current)) {
          return;
        }

        if (next) {
          latestStatusRef.current = next.status;
        }

        if (shouldContinuePolling(latestStatusRef.current)) {
          timerRef.current = window.setTimeout(() => {
            void tick();
          }, pollIntervalMs);
        }
      };

      timerRef.current = window.setTimeout(() => {
        void tick();
      }, pollIntervalMs);
    },
    [pollWhenProcessing, pollIntervalMs, fetchOnce, clearTimer],
  );

  const refresh = useCallback(async (): Promise<AiSession | null> => {
    const requestKey = sessionRequestKey(workspaceId, sessionId);
    if (!requestKey) return null;

    setLoading(true);
    const next = await fetchOnce(requestKey);
    if (shouldApplySessionResponse(activeKeyRef.current, requestKey, cancelledRef.current)) {
      setLoading(false);
      if (next?.status === "PROCESSING") {
        startPollingLoop(requestKey);
      }
    }
    return next;
  }, [workspaceId, sessionId, fetchOnce, startPollingLoop]);

  const setSessionGuarded = useCallback((next: AiSession) => {
    const requestKey = activeKeyRef.current;
    if (!requestKey || cancelledRef.current) return;
    applySession(next, requestKey);
  }, [applySession]);

  useEffect(() => {
    const requestKey = sessionRequestKey(workspaceId, sessionId);
    activeKeyRef.current = requestKey;
    cancelledRef.current = false;
    setLoading(true);
    setError(null);
    setPollError(null);
    setSession(null);
    hasSessionRef.current = false;
    latestStatusRef.current = null;
    clearTimer();

    if (!requestKey) {
      setLoading(false);
      setError("AI 세션을 찾을 수 없습니다.");
      return () => {
        cancelledRef.current = true;
        clearTimer();
      };
    }

    void (async () => {
      await fetchOnce(requestKey);
      if (shouldApplySessionResponse(activeKeyRef.current, requestKey, cancelledRef.current)) {
        setLoading(false);
      }
    })();

    return () => {
      cancelledRef.current = true;
      clearTimer();
    };
    // Intentionally only re-bind when ids change
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [workspaceId, sessionId]);

  useEffect(() => {
    if (!pollWhenProcessing) return;
    const requestKey = sessionRequestKey(workspaceId, sessionId);
    if (!requestKey || requestKey !== activeKeyRef.current) return;
    if (!session || session.status !== "PROCESSING") return;

    latestStatusRef.current = "PROCESSING";
    startPollingLoop(requestKey);

    return () => clearTimer();
  }, [
    session?.status,
    session?.id,
    pollWhenProcessing,
    workspaceId,
    sessionId,
    startPollingLoop,
    clearTimer,
  ]);

  return {
    session,
    setSession: setSessionGuarded,
    loading,
    error,
    pollError,
    refresh,
    clearPollError: () => setPollError(null),
  };
}

export function parseVisibilityParam(raw: string | null): IdeaVisibility {
  if (raw === "PRIVATE" || raw === "WORKSPACE" || raw === "SELECTED_USERS") {
    return raw;
  }
  return "PRIVATE";
}

export function mapProvenanceSource(
  source: string | undefined | null,
): SourceBadgeType | null {
  switch (source) {
    case "USER_INPUT":
      return "user_input";
    case "LLM_SUMMARY":
      return "llm_structured";
    case "LLM_INFERENCE":
      return "llm_inferred";
    case "WEB_EVIDENCE":
      return "web_evidence";
    case "USER_EDIT":
      return "user_edited";
    default:
      return null;
  }
}

export function formatElapsedSince(iso: string | undefined | null): string {
  if (!iso) return "0:00";
  const start = Date.parse(iso);
  if (Number.isNaN(start)) return "0:00";
  const seconds = Math.max(0, Math.floor((Date.now() - start) / 1000));
  const m = Math.floor(seconds / 60);
  const s = seconds % 60;
  return `${m}:${String(s).padStart(2, "0")}`;
}
