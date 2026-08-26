import { Navigate, Outlet, useLocation } from "react-router";
import { useAuth } from "./AuthProvider";
import { buildLoginUrl } from "../utils/routing";

export function RequireAuth() {
  const { status, user } = useAuth();
  const location = useLocation();

  if (status === "loading") {
    return (
      <div className="min-h-screen flex items-center justify-center bg-[#f8f8f9]">
        <p className="text-sm text-[#6b6b80]">로딩 중...</p>
      </div>
    );
  }

  if (status === "error") {
    return (
      <div className="min-h-screen flex items-center justify-center bg-[#f8f8f9] p-4">
        <div className="bg-white rounded-xl border border-[rgba(0,0,0,0.08)] p-6 max-w-md text-center">
          <p className="text-sm text-[#dc2626] mb-2">서버 연결에 실패했습니다.</p>
          <p className="text-xs text-[#6b6b80]">잠시 후 다시 시도해 주세요.</p>
        </div>
      </div>
    );
  }

  if (status === "unauthenticated") {
    const returnTo = location.pathname + location.search;
    return <Navigate to={buildLoginUrl(returnTo)} replace />;
  }

  if (user?.must_change_password && location.pathname !== "/change-password") {
    return <Navigate to="/change-password" replace />;
  }

  return <Outlet />;
}

export function RequireGuest() {
  const { status, user } = useAuth();
  const location = useLocation();

  if (status === "loading") {
    return (
      <div className="min-h-screen flex items-center justify-center bg-[#f8f8f9]">
        <p className="text-sm text-[#6b6b80]">로딩 중...</p>
      </div>
    );
  }

  if (status === "authenticated" && user) {
    if (user.must_change_password) {
      return <Navigate to="/change-password" replace />;
    }
    const params = new URLSearchParams(location.search);
    const returnTo = params.get("returnTo");
    if (returnTo && returnTo.startsWith("/w/")) {
      return <Navigate to={returnTo} replace />;
    }
    return <Navigate to="/w/personal/home" replace />;
  }

  return <Outlet />;
}
