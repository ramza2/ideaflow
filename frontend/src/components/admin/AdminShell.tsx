import { NavLink } from "react-router";
import { clsx } from "clsx";
import { ChevronLeft, Settings, Users, SlidersHorizontal, Cpu } from "lucide-react";

interface AdminShellProps {
  title: string;
  children: React.ReactNode;
}

const NAV_ITEMS = [
  { to: "/admin/users", label: "사용자 관리", icon: Users },
  { to: "/admin/settings", label: "시스템 설정", icon: SlidersHorizontal },
  { to: "/admin/integrations", label: "AI 및 외부 연계", icon: Cpu },
] as const;

export function AdminShell({ title, children }: AdminShellProps) {
  return (
    <div className="min-h-full bg-[#f0f0f5]">
      <div className="bg-[#111118] text-white px-4 sm:px-8 py-4">
        <div className="flex flex-col gap-4 lg:flex-row lg:items-center lg:justify-between">
          <div className="flex items-center gap-4 min-w-0">
            <NavLink
              to="/w/personal/home"
              className="flex items-center gap-1.5 text-white/60 hover:text-white text-sm transition-colors shrink-0"
            >
              <ChevronLeft className="w-4 h-4" />
              앱으로 돌아가기
            </NavLink>
            <div className="w-px h-4 bg-white/20 shrink-0" />
            <div className="flex items-center gap-2 min-w-0">
              <Settings className="w-4 h-4 text-white/60 shrink-0" />
              <span className="text-sm font-medium shrink-0">시스템 관리</span>
              <span className="text-white/30 shrink-0">/</span>
              <span className="text-sm text-white/80 truncate">{title}</span>
            </div>
          </div>
          <nav className="flex gap-1 overflow-x-auto">
            {NAV_ITEMS.map((item) => (
              <NavLink
                key={item.to}
                to={item.to}
                className={({ isActive }) =>
                  clsx(
                    "flex items-center gap-1.5 px-3 py-2 rounded-lg text-sm whitespace-nowrap transition-colors",
                    isActive
                      ? "bg-white/10 text-white"
                      : "text-white/60 hover:text-white hover:bg-white/5",
                  )
                }
              >
                <item.icon className="w-4 h-4" />
                {item.label}
              </NavLink>
            ))}
          </nav>
        </div>
      </div>
      {children}
    </div>
  );
}
