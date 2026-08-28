import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";
import { useNavigate, useParams } from "react-router";
import * as workspaceApi from "../api/workspaces";
import { apiErrorMessage } from "../api/client";
import type { WorkspacePublic } from "../types/api";
import {
  isLegacyPersonalWorkspaceId,
  LEGACY_PERSONAL_WORKSPACE_ID,
} from "../utils/routing";

interface WorkspaceContextValue {
  workspaces: WorkspacePublic[];
  currentWorkspace: WorkspacePublic | null;
  loading: boolean;
  error: string | null;
  refreshWorkspaces: () => Promise<WorkspacePublic[]>;
  setCurrentWorkspaceId: (id: string) => void;
}

const WorkspaceContext = createContext<WorkspaceContextValue | null>(null);

function pickDefaultWorkspace(workspaces: WorkspacePublic[]): WorkspacePublic | null {
  const personal = workspaces.find((w) => w.type === "PERSONAL");
  if (personal) return personal;
  return workspaces[0] ?? null;
}

export function WorkspaceProvider({ children }: { children: ReactNode }) {
  const { workspaceId } = useParams();
  const navigate = useNavigate();
  const [workspaces, setWorkspaces] = useState<WorkspacePublic[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const refreshWorkspaces = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const list = await workspaceApi.listWorkspaces();
      setWorkspaces(list);
      return list;
    } catch (err) {
      setError(apiErrorMessage(err));
      setWorkspaces([]);
      return [];
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void refreshWorkspaces();
  }, [refreshWorkspaces]);

  const currentWorkspace = useMemo(() => {
    if (!workspaceId || isLegacyPersonalWorkspaceId(workspaceId)) {
      return pickDefaultWorkspace(workspaces);
    }
    return workspaces.find((w) => w.id === workspaceId) ?? null;
  }, [workspaceId, workspaces]);

  // Legacy /w/personal/* → real PERSONAL workspace UUID
  useEffect(() => {
    if (!workspaceId || !isLegacyPersonalWorkspaceId(workspaceId)) return;
    if (loading) return;
    const personal = workspaces.find((w) => w.type === "PERSONAL");
    if (personal) {
      const rest = window.location.pathname.replace(
        `/w/${LEGACY_PERSONAL_WORKSPACE_ID}`,
        `/w/${personal.id}`,
      );
      navigate(`${rest}${window.location.search}`, { replace: true });
    }
  }, [workspaceId, workspaces, loading, navigate]);

  // Invalid workspace UUID → fallback
  useEffect(() => {
    if (!workspaceId || isLegacyPersonalWorkspaceId(workspaceId)) return;
    if (loading || workspaces.length === 0) return;
    const exists = workspaces.some((w) => w.id === workspaceId);
    if (!exists) {
      const fallback = pickDefaultWorkspace(workspaces);
      if (fallback) {
        const rest = window.location.pathname.replace(
          `/w/${workspaceId}`,
          `/w/${fallback.id}`,
        );
        navigate(`${rest}${window.location.search}`, { replace: true });
      }
    }
  }, [workspaceId, workspaces, loading, navigate]);

  const setCurrentWorkspaceId = useCallback(
    (id: string) => {
      // AI session URLs are bound to workspace+session — do not carry sessionId across workspaces
      if (/\/ideas\/new\/ai\/(analyzing|review)(\/|$)/.test(window.location.pathname)) {
        navigate(`/w/${id}/ideas/new/ai`, { replace: true });
        return;
      }
      navigate(`/w/${id}/home`);
    },
    [navigate],
  );

  const isResolvingLegacy =
    !!workspaceId &&
    isLegacyPersonalWorkspaceId(workspaceId) &&
    !loading &&
    workspaces.some((w) => w.type === "PERSONAL");

  const value = useMemo(
    () => ({
      workspaces,
      currentWorkspace,
      loading: loading || isResolvingLegacy,
      error,
      refreshWorkspaces,
      setCurrentWorkspaceId,
    }),
    [workspaces, currentWorkspace, loading, isResolvingLegacy, error, refreshWorkspaces, setCurrentWorkspaceId],
  );

  return (
    <WorkspaceContext.Provider value={value}>
      {loading || isResolvingLegacy ? (
        <div className="min-h-screen flex items-center justify-center bg-[#f8f8f9]">
          <p className="text-sm text-[#6b6b80]">작업공간 불러오는 중...</p>
        </div>
      ) : (
        children
      )}
    </WorkspaceContext.Provider>
  );
}

export function useWorkspace(): WorkspaceContextValue {
  const ctx = useContext(WorkspaceContext);
  if (!ctx) {
    throw new Error("useWorkspace must be used within WorkspaceProvider");
  }
  return ctx;
}

export function WorkspaceEmptyState() {
  return (
    <div className="min-h-[60vh] flex items-center justify-center p-8">
      <div className="text-center max-w-md">
        <p className="text-lg font-semibold text-[#111118] mb-2">
          사용 가능한 작업공간이 없습니다.
        </p>
        <p className="text-sm text-[#6b6b80]">
          관리자에게 문의하거나 잠시 후 다시 시도해 주세요.
        </p>
      </div>
    </div>
  );
}
