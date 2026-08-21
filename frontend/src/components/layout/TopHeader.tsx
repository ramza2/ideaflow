import { useState, useRef, useEffect } from "react";
import { useNavigate } from "react-router";
import { clsx } from "clsx";
import {
  Search,
  Bell,
  Plus,
  Sparkles,
  PenLine,
  FileInput,
  ChevronDown,
  Check,
  Menu,
  X,
  LogOut,
  User,
  Shield,
} from "lucide-react";
import { MOCK_WORKSPACES, getWorkspaceById } from "../../mocks/workspaces";
import { CURRENT_USER } from "../../mocks/users";
import { MOCK_NOTIFICATIONS } from "../../mocks/notifications";
import { Avatar } from "../common/Avatar";
import { Button } from "../common/Button";

interface TopHeaderProps {
  workspaceId: string;
  onWorkspaceChange: (id: string) => void;
  onMobileMenuToggle: () => void;
}

export function TopHeader({ workspaceId, onWorkspaceChange, onMobileMenuToggle }: TopHeaderProps) {
  const navigate = useNavigate();
  const [wsOpen, setWsOpen] = useState(false);
  const [createOpen, setCreateOpen] = useState(false);
  const [notifOpen, setNotifOpen] = useState(false);
  const [profileOpen, setProfileOpen] = useState(false);

  const ws = getWorkspaceById(workspaceId);
  const unreadCount = MOCK_NOTIFICATIONS.filter((n) => !n.read).length;

  const wsRef = useRef<HTMLDivElement>(null);
  const createRef = useRef<HTMLDivElement>(null);
  const notifRef = useRef<HTMLDivElement>(null);
  const profileRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    function handler(e: MouseEvent) {
      if (wsRef.current && !wsRef.current.contains(e.target as Node)) setWsOpen(false);
      if (createRef.current && !createRef.current.contains(e.target as Node)) setCreateOpen(false);
      if (notifRef.current && !notifRef.current.contains(e.target as Node)) setNotifOpen(false);
      if (profileRef.current && !profileRef.current.contains(e.target as Node)) setProfileOpen(false);
    }
    document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, []);

  return (
    <header className="h-16 bg-white border-b border-[rgba(0,0,0,0.07)] flex items-center px-4 gap-3 shrink-0 z-20 relative">
      {/* Mobile menu */}
      <button
        className="md:hidden p-1.5 rounded-lg text-[#6b6b80] hover:bg-[#f4f4f8]"
        onClick={onMobileMenuToggle}
      >
        <Menu className="w-5 h-5" />
      </button>

      {/* Workspace switcher */}
      <div ref={wsRef} className="relative">
        <button
          onClick={() => setWsOpen(!wsOpen)}
          className="flex items-center gap-2 px-2.5 py-1.5 rounded-lg hover:bg-[#f4f4f8] transition-colors"
        >
          <span className="text-base">{ws?.icon}</span>
          <div className="text-left hidden sm:block">
            <p className="text-sm font-semibold text-[#111118] leading-tight">{ws?.name}</p>
            <p className="text-xs text-[#6b6b80] leading-tight">
              {ws?.type === "personal" ? "개인" : "팀"}
            </p>
          </div>
          <ChevronDown className="w-3.5 h-3.5 text-[#6b6b80]" />
        </button>

        {wsOpen && (
          <div className="absolute top-full left-0 mt-1 w-56 bg-white rounded-xl border border-[rgba(0,0,0,0.08)] shadow-lg py-1 z-50">
            <p className="text-xs font-medium text-[#6b6b80] px-3 py-1.5 uppercase tracking-wider">개인 작업공간</p>
            {MOCK_WORKSPACES.filter((w) => w.type === "personal").map((w) => (
              <button
                key={w.id}
                onClick={() => { onWorkspaceChange(w.id); setWsOpen(false); }}
                className="w-full flex items-center gap-2.5 px-3 py-2 hover:bg-[#f4f4f8] text-sm"
              >
                <span>{w.icon}</span>
                <span className="flex-1 text-left">{w.name}</span>
                {w.id === workspaceId && <Check className="w-3.5 h-3.5 text-[#4f46e5]" />}
              </button>
            ))}
            <p className="text-xs font-medium text-[#6b6b80] px-3 py-1.5 mt-1 uppercase tracking-wider">팀 작업공간</p>
            {MOCK_WORKSPACES.filter((w) => w.type === "team").map((w) => (
              <button
                key={w.id}
                onClick={() => { onWorkspaceChange(w.id); setWsOpen(false); }}
                className="w-full flex items-center gap-2.5 px-3 py-2 hover:bg-[#f4f4f8] text-sm"
              >
                <span>{w.icon}</span>
                <span className="flex-1 text-left">{w.name}</span>
                {w.id === workspaceId && <Check className="w-3.5 h-3.5 text-[#4f46e5]" />}
              </button>
            ))}
            <div className="border-t border-[rgba(0,0,0,0.06)] mt-1 pt-1">
              <button className="w-full text-left px-3 py-2 text-sm text-[#6b6b80] hover:bg-[#f4f4f8]">+ 새 작업공간 만들기</button>
              <button className="w-full text-left px-3 py-2 text-sm text-[#6b6b80] hover:bg-[#f4f4f8]">작업공간 관리</button>
            </div>
          </div>
        )}
      </div>

      {/* Search */}
      <div className="flex-1 max-w-lg mx-auto hidden md:block">
        <div className="relative">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-[#9ca3af]" />
          <input
            type="text"
            placeholder="아이디어를 검색하거나 자연어로 질문하세요"
            className="w-full h-9 pl-9 pr-12 rounded-lg bg-[#f4f4f8] border border-transparent text-sm text-[#111118] placeholder:text-[#9ca3af] focus:outline-none focus:bg-white focus:border-[rgba(0,0,0,0.1)] focus:ring-2 focus:ring-[#4f46e5]/10 transition-all"
          />
          <div className="absolute right-3 top-1/2 -translate-y-1/2 flex items-center">
            <kbd className="text-[10px] font-mono text-[#9ca3af] bg-white border border-[rgba(0,0,0,0.1)] px-1.5 py-0.5 rounded">/</kbd>
          </div>
        </div>
      </div>

      <div className="flex items-center gap-1.5 ml-auto">
        {/* Create button */}
        <div ref={createRef} className="relative">
          <Button
            variant="primary"
            size="sm"
            icon={<Plus className="w-3.5 h-3.5" />}
            onClick={() => setCreateOpen(!createOpen)}
          >
            <span className="hidden sm:inline">새 아이디어</span>
          </Button>
          {createOpen && (
            <div className="absolute top-full right-0 mt-1 w-52 bg-white rounded-xl border border-[rgba(0,0,0,0.08)] shadow-lg py-1 z-50">
              <button
                onClick={() => { navigate(`/w/${workspaceId}/ideas/new/ai`); setCreateOpen(false); }}
                className="w-full flex items-center gap-2.5 px-3 py-2.5 hover:bg-[#f5f3ff] group"
              >
                <div className="w-7 h-7 rounded-lg bg-[#ede9fe] flex items-center justify-center">
                  <Sparkles className="w-4 h-4 text-[#7c3aed]" />
                </div>
                <div className="text-left">
                  <p className="text-sm font-semibold text-[#7c3aed]">AI로 빠르게 등록</p>
                  <p className="text-xs text-[#6b6b80]">자연어로 입력</p>
                </div>
              </button>
              <button
                onClick={() => { navigate(`/w/${workspaceId}/ideas/new`); setCreateOpen(false); }}
                className="w-full flex items-center gap-2.5 px-3 py-2.5 hover:bg-[#f4f4f8]"
              >
                <div className="w-7 h-7 rounded-lg bg-[#f0f0f5] flex items-center justify-center">
                  <PenLine className="w-4 h-4 text-[#6b6b80]" />
                </div>
                <p className="text-sm text-[#111118]">직접 등록</p>
              </button>
              <button className="w-full flex items-center gap-2.5 px-3 py-2.5 hover:bg-[#f4f4f8]">
                <div className="w-7 h-7 rounded-lg bg-[#f0f0f5] flex items-center justify-center">
                  <FileInput className="w-4 h-4 text-[#6b6b80]" />
                </div>
                <p className="text-sm text-[#111118]">텍스트·파일 가져오기</p>
              </button>
            </div>
          )}
        </div>

        {/* Notifications */}
        <div ref={notifRef} className="relative">
          <button
            onClick={() => setNotifOpen(!notifOpen)}
            className="w-8 h-8 flex items-center justify-center rounded-lg text-[#6b6b80] hover:bg-[#f4f4f8] relative transition-colors"
          >
            <Bell className="w-4.5 h-4.5" />
            {unreadCount > 0 && (
              <span className="absolute top-1 right-1 w-2 h-2 rounded-full bg-[#dc2626]" />
            )}
          </button>
          {notifOpen && (
            <div className="absolute top-full right-0 mt-1 w-80 bg-white rounded-xl border border-[rgba(0,0,0,0.08)] shadow-lg z-50">
              <div className="flex items-center justify-between px-4 py-3 border-b border-[rgba(0,0,0,0.06)]">
                <p className="text-sm font-semibold text-[#111118]">알림</p>
                <button className="text-xs text-[#4f46e5] hover:underline">모두 읽음</button>
              </div>
              <div className="max-h-80 overflow-y-auto">
                {MOCK_NOTIFICATIONS.map((n) => (
                  <div
                    key={n.id}
                    className={clsx(
                      "px-4 py-3 border-b border-[rgba(0,0,0,0.04)] hover:bg-[#f8f8fb] cursor-pointer",
                      !n.read && "bg-[#f5f3ff]/50"
                    )}
                  >
                    <p className="text-sm font-medium text-[#111118] mb-0.5">{n.title}</p>
                    <p className="text-xs text-[#6b6b80] line-clamp-2">{n.body}</p>
                    {!n.read && (
                      <span className="inline-block w-1.5 h-1.5 rounded-full bg-[#4f46e5] mt-1.5" />
                    )}
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>

        {/* Profile */}
        <div ref={profileRef} className="relative">
          <button
            onClick={() => setProfileOpen(!profileOpen)}
            className="rounded-full hover:ring-2 hover:ring-[#4f46e5]/20 transition-all"
          >
            <Avatar user={CURRENT_USER} size="sm" />
          </button>
          {profileOpen && (
            <div className="absolute top-full right-0 mt-1 w-52 bg-white rounded-xl border border-[rgba(0,0,0,0.08)] shadow-lg py-1 z-50">
              <div className="px-3 py-2.5 border-b border-[rgba(0,0,0,0.06)]">
                <p className="text-sm font-semibold text-[#111118]">{CURRENT_USER.name}</p>
                <p className="text-xs text-[#6b6b80]">{CURRENT_USER.email}</p>
              </div>
              <button className="w-full flex items-center gap-2.5 px-3 py-2 text-sm text-[#111118] hover:bg-[#f4f4f8]">
                <User className="w-4 h-4 text-[#6b6b80]" /> 프로필
              </button>
              <button
                onClick={() => { navigate("/admin/integrations"); setProfileOpen(false); }}
                className="w-full flex items-center gap-2.5 px-3 py-2 text-sm text-[#111118] hover:bg-[#f4f4f8]"
              >
                <Shield className="w-4 h-4 text-[#6b6b80]" /> 시스템 관리
              </button>
              <div className="border-t border-[rgba(0,0,0,0.06)] mt-1 pt-1">
                <button
                  onClick={() => navigate("/login")}
                  className="w-full flex items-center gap-2.5 px-3 py-2 text-sm text-[#dc2626] hover:bg-[#fef2f2]"
                >
                  <LogOut className="w-4 h-4" /> 로그아웃
                </button>
              </div>
            </div>
          )}
        </div>
      </div>
    </header>
  );
}
