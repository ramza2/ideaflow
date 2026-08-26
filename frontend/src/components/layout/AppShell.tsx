import { useState } from "react";
import { Outlet, useNavigate, useParams } from "react-router";
import { clsx } from "clsx";
import { TopHeader } from "./TopHeader";
import { Sidebar } from "./Sidebar";
import { ToastContainer } from "../common/Toast";
import { useWorkspace, WorkspaceEmptyState } from "../../workspace/WorkspaceProvider";

export function AppShell() {
  const navigate = useNavigate();
  const { workspaceId } = useParams();
  const { workspaces, currentWorkspace, loading, error } = useWorkspace();
  const [collapsed, setCollapsed] = useState(false);
  const [mobileOpen, setMobileOpen] = useState(false);

  const effectiveWorkspaceId = currentWorkspace?.id ?? workspaceId ?? "";

  function handleWorkspaceChange(id: string) {
    navigate(`/w/${id}/home`);
  }

  if (!loading && workspaces.length === 0) {
    return (
      <div className="flex flex-col h-screen overflow-hidden bg-[#f8f8f9]">
        <div className="h-16 bg-white border-b border-[rgba(0,0,0,0.07)] flex items-center px-4">
          <span className="text-sm font-semibold text-[#111118]">IdeaFlow</span>
        </div>
        {error ? (
          <div className="flex-1 flex items-center justify-center p-8">
            <p className="text-sm text-[#dc2626]">{error}</p>
          </div>
        ) : (
          <WorkspaceEmptyState />
        )}
      </div>
    );
  }

  return (
    <div className="flex flex-col h-screen overflow-hidden bg-[#f8f8f9]">
      <TopHeader
        workspaceId={effectiveWorkspaceId}
        onWorkspaceChange={handleWorkspaceChange}
        onMobileMenuToggle={() => setMobileOpen(!mobileOpen)}
      />
      <div className="flex flex-1 overflow-hidden relative">
        {mobileOpen && (
          <div
            className="fixed inset-0 bg-black/30 z-30 md:hidden"
            onClick={() => setMobileOpen(false)}
          />
        )}
        <div
          className={clsx(
            "md:relative fixed inset-y-0 left-0 z-40 md:z-auto transition-transform duration-200",
            "md:translate-x-0",
            mobileOpen ? "translate-x-0" : "-translate-x-full md:translate-x-0",
          )}
        >
          <Sidebar
            workspaceId={effectiveWorkspaceId}
            collapsed={collapsed}
            onToggle={() => setCollapsed(!collapsed)}
          />
        </div>

        <main className="flex-1 overflow-y-auto">
          <Outlet />
        </main>
      </div>
      <ToastContainer />
    </div>
  );
}
