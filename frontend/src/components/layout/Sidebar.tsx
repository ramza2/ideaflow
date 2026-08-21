import { useState } from "react";
import { NavLink, useNavigate } from "react-router";
import { clsx } from "clsx";
import {
  Home,
  Lightbulb,
  ClipboardCheck,
  Settings,
  Building2,
  HelpCircle,
  ChevronLeft,
  ChevronRight,
} from "lucide-react";
import { MOCK_IDEAS } from "../../mocks/ideas";

interface SidebarProps {
  workspaceId: string;
  collapsed: boolean;
  onToggle: () => void;
}

const reviewCount = MOCK_IDEAS.filter(
  (i) => i.stage === "reviewing"
).length;

export function Sidebar({ workspaceId, collapsed, onToggle }: SidebarProps) {
  const base = `/w/${workspaceId}`;

  const navItems = [
    { label: "홈", icon: Home, to: `${base}/home` },
    { label: "아이디어", icon: Lightbulb, to: `${base}/ideas` },
    {
      label: "검토함",
      icon: ClipboardCheck,
      to: `${base}/reviews`,
      badge: reviewCount,
    },
    { label: "작업공간", icon: Building2, to: `${base}/settings/members` },
    { label: "설정", icon: Settings, to: `${base}/settings` },
  ];

  return (
    <aside
      className={clsx(
        "flex flex-col bg-white border-r border-[rgba(0,0,0,0.07)] transition-all duration-200 shrink-0",
        collapsed ? "w-[72px]" : "w-[240px]"
      )}
    >
      <nav className="flex-1 py-3 px-2 space-y-0.5">
        {navItems.map((item) => (
          <NavLink
            key={item.to}
            to={item.to}
            className={({ isActive }) =>
              clsx(
                "flex items-center gap-3 px-2.5 py-2 rounded-lg text-sm font-medium transition-colors group",
                isActive
                  ? "bg-[#ede9fe] text-[#4f46e5]"
                  : "text-[#6b6b80] hover:bg-[#f4f4f8] hover:text-[#111118]",
                collapsed && "justify-center px-0"
              )
            }
            title={collapsed ? item.label : undefined}
          >
            <item.icon className="w-4.5 h-4.5 shrink-0" />
            {!collapsed && (
              <>
                <span className="flex-1">{item.label}</span>
                {item.badge ? (
                  <span className="min-w-[18px] h-[18px] px-1 rounded-full bg-[#d97706] text-white text-[10px] font-bold flex items-center justify-center">
                    {item.badge}
                  </span>
                ) : null}
              </>
            )}
            {collapsed && item.badge ? (
              <span className="absolute top-1 right-1 w-2 h-2 rounded-full bg-[#d97706]" />
            ) : null}
          </NavLink>
        ))}
      </nav>

      <div className="px-2 py-3 border-t border-[rgba(0,0,0,0.06)] space-y-0.5">
        <NavLink
          to={`${base}/help`}
          className={({ isActive }) =>
            clsx(
              "w-full flex items-center gap-3 px-2.5 py-2 rounded-lg text-sm font-medium transition-colors",
              isActive
                ? "bg-[#ede9fe] text-[#4f46e5]"
                : "text-[#6b6b80] hover:bg-[#f4f4f8] hover:text-[#111118]",
              collapsed && "justify-center px-0"
            )
          }
          title={collapsed ? "도움말" : undefined}
        >
          <HelpCircle className="w-4.5 h-4.5 shrink-0" />
          {!collapsed && <span>도움말</span>}
        </NavLink>
        <button
          onClick={onToggle}
          className={clsx(
            "w-full flex items-center gap-3 px-2.5 py-2 rounded-lg text-sm text-[#6b6b80] hover:bg-[#f4f4f8] hover:text-[#111118] transition-colors",
            collapsed && "justify-center px-0"
          )}
          title={collapsed ? "펼치기" : undefined}
        >
          {collapsed ? (
            <ChevronRight className="w-4.5 h-4.5 shrink-0" />
          ) : (
            <>
              <ChevronLeft className="w-4.5 h-4.5 shrink-0" />
              <span>사이드바 접기</span>
            </>
          )}
        </button>
      </div>
    </aside>
  );
}
