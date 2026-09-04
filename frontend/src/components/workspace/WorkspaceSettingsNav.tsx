import { NavLink } from "react-router";
import { clsx } from "clsx";
import { useWorkspace } from "../../workspace/WorkspaceProvider";

const TABS = [
  { label: "일반", path: "general" },
  { label: "구성원", path: "members" },
  { label: "단계", path: "stages" },
  { label: "카테고리", path: "categories" },
] as const;

export function WorkspaceSettingsNav() {
  const { currentWorkspace } = useWorkspace();
  const base = currentWorkspace ? `/w/${currentWorkspace.id}/workspace` : "";

  return (
    <div className="bg-white border-b border-[rgba(0,0,0,0.07)]">
      <div className="px-4 sm:px-8 pt-5 pb-0">
        <h1 className="text-xl font-bold text-[#111118]">작업공간 설정</h1>
        <p className="text-sm text-[#6b6b80] mt-1 mb-4">
          {currentWorkspace?.name ?? "작업공간"} · {currentWorkspace?.type === "PERSONAL" ? "개인" : "팀"}
        </p>
        <div className="flex gap-1 overflow-x-auto">
          {TABS.map((tab) => (
            <NavLink
              key={tab.path}
              to={`${base}/${tab.path}`}
              className={({ isActive }) =>
                clsx(
                  "px-4 py-2.5 text-sm font-medium border-b-2 transition-colors whitespace-nowrap",
                  isActive
                    ? "border-[#4f46e5] text-[#4f46e5]"
                    : "border-transparent text-[#6b6b80] hover:text-[#111118]",
                )
              }
            >
              {tab.label}
            </NavLink>
          ))}
        </div>
      </div>
    </div>
  );
}
