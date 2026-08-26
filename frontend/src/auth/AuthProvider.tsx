import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";
import { useNavigate } from "react-router";
import * as authApi from "../api/auth";
import { ApiError, setUnauthorizedHandler } from "../api/client";
import type { UserPublic } from "../types/api";
import { buildLoginUrl } from "../utils/routing";

export type AuthStatus = "loading" | "authenticated" | "unauthenticated" | "error";

interface AuthContextValue {
  status: AuthStatus;
  user: UserPublic | null;
  error: string | null;
  login: (email: string, password: string) => Promise<UserPublic>;
  logout: () => Promise<void>;
  refreshUser: () => Promise<UserPublic | null>;
  clearAuth: () => void;
}

const AuthContext = createContext<AuthContextValue | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const navigate = useNavigate();
  const [status, setStatus] = useState<AuthStatus>("loading");
  const [user, setUser] = useState<UserPublic | null>(null);
  const [error, setError] = useState<string | null>(null);

  const clearAuth = useCallback(() => {
    setUser(null);
    setStatus("unauthenticated");
  }, []);

  const refreshUser = useCallback(async (): Promise<UserPublic | null> => {
    try {
      const me = await authApi.fetchMe();
      setUser(me);
      setStatus("authenticated");
      setError(null);
      return me;
    } catch (err) {
      if (err instanceof ApiError && err.status === 401) {
        clearAuth();
        return null;
      }
      setStatus("error");
      setError(err instanceof Error ? err.message : "인증 상태를 확인할 수 없습니다.");
      return null;
    }
  }, [clearAuth]);

  useEffect(() => {
    void refreshUser();
  }, [refreshUser]);

  useEffect(() => {
    setUnauthorizedHandler(() => {
      clearAuth();
      const returnTo = window.location.pathname + window.location.search;
      navigate(buildLoginUrl(returnTo), { replace: true });
    });
    return () => setUnauthorizedHandler(null);
  }, [clearAuth, navigate]);

  const login = useCallback(async (email: string, password: string) => {
    const result = await authApi.login(email, password);
    setUser(result.user);
    setStatus("authenticated");
    setError(null);
    return result.user;
  }, []);

  const logout = useCallback(async () => {
    try {
      await authApi.logout();
    } catch {
      // Session may already be invalid; still clear local state.
    }
    clearAuth();
  }, [clearAuth]);

  const value = useMemo(
    () => ({ status, user, error, login, logout, refreshUser, clearAuth }),
    [status, user, error, login, logout, refreshUser, clearAuth],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext);
  if (!ctx) {
    throw new Error("useAuth must be used within AuthProvider");
  }
  return ctx;
}
