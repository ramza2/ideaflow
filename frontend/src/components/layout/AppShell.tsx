import { useState } from "react";
import { Outlet, useNavigate, useParams } from "react-router";
import { clsx } from "clsx";
import { TopHeader } from "./TopHeader";
import { Sidebar } from "./Sidebar";
import { ToastContainer } from "../common/Toast";

export function AppShell() {
  const navigate = useNavigate();
  const { workspaceId = "personal" } = useParams();
  const [collapsed, setCollapsed] = useState(false);
  const [mobileOpen, setMobileOpen] = useState(false);

  function handleWorkspaceChange(id: string) {
    navigate(`/w/${id}/home`);
  }

  return (
    <div className="flex flex-col h-screen overflow-hidden bg-[#f8f8f9]">
      <TopHeader
        workspaceId={workspaceId}
        onWorkspaceChange={handleWorkspaceChange}
        onMobileMenuToggle={() => setMobileOpen(!mobileOpen)}
      />
      <div className="flex flex-1 overflow-hidden relative">
        {/* Mobile overlay */}
        {mobileOpen && (
          <div
            className="fixed inset-0 bg-black/30 z-30 md:hidden"
            onClick={() => setMobileOpen(false)}
          />
        )}
        {/* Sidebar — hidden on mobile, shown in drawer when mobileOpen */}
        <div
          className={clsx(
            "md:relative fixed inset-y-0 left-0 z-40 md:z-auto transition-transform duration-200",
            "md:translate-x-0",
            mobileOpen ? "translate-x-0" : "-translate-x-full md:translate-x-0"
          )}
        >
          <Sidebar
            workspaceId={workspaceId}
            collapsed={collapsed}
            onToggle={() => setCollapsed(!collapsed)}
          />
        </div>

        {/* Main content */}
        <main className="flex-1 overflow-y-auto">
          <Outlet />
        </main>
      </div>
      <ToastContainer />
    </div>
  );
}
