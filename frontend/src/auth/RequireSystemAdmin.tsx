import { Navigate, Outlet } from "react-router";
import { useAuth } from "./AuthProvider";

export function RequireSystemAdmin() {
  const { status, user } = useAuth();

  if (status === "loading") {
    return (
      <div className="min-h-screen flex items-center justify-center bg-[#f0f0f5]">
        <p className="text-sm text-[#6b6b80]">로딩 중...</p>
      </div>
    );
  }

  if (status !== "authenticated" || user?.system_role !== "SYSTEM_ADMIN") {
    return <Navigate to="/w/personal/home" replace />;
  }

  return <Outlet />;
}
