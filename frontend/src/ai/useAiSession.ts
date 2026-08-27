import { useCallback, useEffect, useRef, useState } from "react";
import { getAiSession } from "../api/aiSessions";
import { apiErrorMessage, ApiError } from "../api/client";
import type { AiSession, IdeaVisibility } from "../types/api";
import type { SourceBadgeType } from "../types";

const DEFAULT_POLL_MS = 1800;

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

  const cancelledRef = useRef(false);
  const timerRef = useRef<number | null>(null);
  const inFlightRef = useRef(false);
  const hasSessionRef = useRef(false);

  const clearTimer = useCallback(() => {
    if (timerRef.current != null) {
      window.clearTimeout(timerRef.current);
      timerRef.current = null;
    }
  }, []);

  const applySession = useCallback((next: AiSession) => {
    hasSessionRef.current = true;
    setSession(next);
    setError(null);
    setPollError(null);
  }, []);

  const fetchOnce = useCallback(async (): Promise<AiSession | null> => {
    if (!workspaceId || !sessionId) return null;
    if (inFlightRef.current) return null;
    inFlightRef.current = true;
    try {
      const next = await getAiSession(workspaceId, sessionId);
      if (cancelledRef.current) return null;
      applySession(next);
      return next;
    } catch (err) {
      if (cancelledRef.current) return null;
      const message = apiErrorMessage(err, "AI 세션을 불러오지 못했습니다.");
      if (err instanceof ApiError && err.status === 404) {
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
      inFlightRef.current = false;
    }
  }, [workspaceId, sessionId, applySession]);

  const refresh = useCallback(async () => {
    setLoading(true);
    await fetchOnce();
    if (!cancelledRef.current) setLoading(false);
  }, [fetchOnce]);

  useEffect(() => {
    cancelledRef.current = false;
    setLoading(true);
    setError(null);
    setPollError(null);
    setSession(null);
    hasSessionRef.current = false;
    clearTimer();

    if (!workspaceId || !sessionId) {
      setLoading(false);
      setError("AI 세션을 찾을 수 없습니다.");
      return () => {
        cancelledRef.current = true;
        clearTimer();
      };
    }

    void (async () => {
      await fetchOnce();
      if (!cancelledRef.current) setLoading(false);
    })();

    return () => {
      cancelledRef.current = true;
      clearTimer();
    };
    // Intentionally only re-bind when ids change
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [workspaceId, sessionId]);

  useEffect(() => {
    clearTimer();
    if (!pollWhenProcessing) return;
    if (!session || session.status !== "PROCESSING") return;
    if (!workspaceId || !sessionId) return;

    const schedule = () => {
      timerRef.current = window.setTimeout(async () => {
        const next = await fetchOnce();
        if (cancelledRef.current) return;
        if (next?.status === "PROCESSING") schedule();
      }, pollIntervalMs);
    };
    schedule();

    return () => clearTimer();
  }, [
    session?.status,
    session?.id,
    pollWhenProcessing,
    pollIntervalMs,
    workspaceId,
    sessionId,
    fetchOnce,
    clearTimer,
  ]);

  return {
    session,
    setSession,
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
): SourceBadgeType {
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
      return "llm_structured";
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
