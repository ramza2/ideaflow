import { useState, useRef, useEffect, FormEvent } from "react";
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
  LogOut,
  User,
  Shield,
} from "lucide-react";
import { MOCK_NOTIFICATIONS } from "../../mocks/notifications";
import { Avatar } from "../common/Avatar";
import { Button } from "../common/Button";
import { toast } from "../common/Toast";
import { useAuth } from "../../auth/AuthProvider";
import { useWorkspace } from "../../workspace/WorkspaceProvider";
import { createTeamWorkspace } from "../../api/workspaces";
import { apiErrorMessage } from "../../api/client";
import { toDisplayUser } from "../../utils/avatar";
import { workspaceIcon } from "../../utils/mappers";

interface TopHeaderProps {
  workspaceId: string;
  onWorkspaceChange: (id: string) => void;
  onMobileMenuToggle: () => void;
}

export function TopHeader({ workspaceId, onWorkspaceChange, onMobileMenuToggle }: TopHeaderProps) {
  const navigate = useNavigate();
  const { user, logout } = useAuth();
  const { workspaces, refreshWorkspaces } = useWorkspace();
  const [wsOpen, setWsOpen] = useState(false);
  const [createOpen, setCreateOpen] = useState(false);
  const [createWsOpen, setCreateWsOpen] = useState(false);
  const [newWsName, setNewWsName] = useState("");
  const [creatingWs, setCreatingWs] = useState(false);
  const [globalSearch, setGlobalSearch] = useState("");
  const [notifOpen, setNotifOpen] = useState(false);
  const [profileOpen, setProfileOpen] = useState(false);

  const ws = workspaces.find((w) => w.id === workspaceId);
  const displayUser = user ? toDisplayUser({ id: user.id, name: user.name, email: user.email }) : null;
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

  async function handleLogout() {
    setProfileOpen(false);
    try {
      await logout();
      navigate("/login", { replace: true });
    } catch (err) {
      toast.error(apiErrorMessage(err, "로그아웃에 실패했습니다."));
    }
  }

  function handleGlobalSearch(e: FormEvent) {
    e.preventDefault();
    const q = globalSearch.trim();
    if (!workspaceId) return;
    navigate(q ? `/w/${workspaceId}/ideas?q=${encodeURIComponent(q)}` : `/w/${workspaceId}/ideas`);
  }

  async function handleCreateWorkspace() {
    const name = newWsName.trim();
    if (!name) return;
    setCreatingWs(true);
    try {
      const created = await createTeamWorkspace({ name });
      await refreshWorkspaces();
      setCreateWsOpen(false);
      setNewWsName("");
      setWsOpen(false);
      toast.success("작업공간이 생성되었습니다.");
      onWorkspaceChange(created.id);
    } catch (err) {
      toast.error(apiErrorMessage(err, "작업공간 생성에 실패했습니다."));
    } finally {
      setCreatingWs(false);
    }
  }

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
          <span className="text-base">{ws ? workspaceIcon(ws.type) : "🏠"}</span>
          <div className="text-left hidden sm:block">
            <p className="text-sm font-semibold text-[#111118] leading-tight">{ws?.name ?? "작업공간"}</p>
            <p className="text-xs text-[#6b6b80] leading-tight">
              {ws?.type === "PERSONAL" ? "개인" : "팀"}
            </p>
          </div>
          <ChevronDown className="w-3.5 h-3.5 text-[#6b6b80]" />
        </button>

        {wsOpen && (
          <div className="absolute top-full left-0 mt-1 w-56 bg-white rounded-xl border border-[rgba(0,0,0,0.08)] shadow-lg py-1 z-50">
            <p className="text-xs font-medium text-[#6b6b80] px-3 py-1.5 uppercase tracking-wider">개인 작업공간</p>
            {workspaces.filter((w) => w.type === "PERSONAL").map((w) => (
              <button
                key={w.id}
                onClick={() => { onWorkspaceChange(w.id); setWsOpen(false); }}
                className="w-full flex items-center gap-2.5 px-3 py-2 hover:bg-[#f4f4f8] text-sm"
              >
                <span>{workspaceIcon(w.type)}</span>
                <span className="flex-1 text-left">{w.name}</span>
                {w.id === workspaceId && <Check className="w-3.5 h-3.5 text-[#4f46e5]" />}
              </button>
            ))}
            <p className="text-xs font-medium text-[#6b6b80] px-3 py-1.5 mt-1 uppercase tracking-wider">팀 작업공간</p>
            {workspaces.filter((w) => w.type === "TEAM").map((w) => (
              <button
                key={w.id}
                onClick={() => { onWorkspaceChange(w.id); setWsOpen(false); }}
                className="w-full flex items-center gap-2.5 px-3 py-2 hover:bg-[#f4f4f8] text-sm"
              >
                <span>{workspaceIcon(w.type)}</span>
                <span className="flex-1 text-left">{w.name}</span>
                {w.id === workspaceId && <Check className="w-3.5 h-3.5 text-[#4f46e5]" />}
              </button>
            ))}
            <div className="border-t border-[rgba(0,0,0,0.06)] mt-1 pt-1">
              <button
                type="button"
                onClick={() => { setCreateWsOpen(true); setWsOpen(false); }}
                className="w-full text-left px-3 py-2 text-sm text-[#6b6b80] hover:bg-[#f4f4f8]"
              >
                + 새 작업공간 만들기
              </button>
            </div>
          </div>
        )}
      </div>

      {/* Search */}
      <form onSubmit={handleGlobalSearch} className="flex-1 max-w-lg mx-auto hidden md:block">
        <div className="relative">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-[#9ca3af]" />
          <input
            type="text"
            value={globalSearch}
            onChange={(e) => setGlobalSearch(e.target.value)}
            placeholder="아이디어를 검색하거나 자연어로 질문하세요"
            disabled={!workspaceId}
            className="w-full h-9 pl-9 pr-12 rounded-lg bg-[#f4f4f8] border border-transparent text-sm text-[#111118] placeholder:text-[#9ca3af] focus:outline-none focus:bg-white focus:border-[rgba(0,0,0,0.1)] focus:ring-2 focus:ring-[#4f46e5]/10 transition-all disabled:opacity-50"
          />
          <div className="absolute right-3 top-1/2 -translate-y-1/2 flex items-center">
            <kbd className="text-[10px] font-mono text-[#9ca3af] bg-white border border-[rgba(0,0,0,0.1)] px-1.5 py-0.5 rounded">/</kbd>
          </div>
        </div>
      </form>

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
            {displayUser && <Avatar user={displayUser} size="sm" />}
          </button>
          {profileOpen && displayUser && (
            <div className="absolute top-full right-0 mt-1 w-52 bg-white rounded-xl border border-[rgba(0,0,0,0.08)] shadow-lg py-1 z-50">
              <div className="px-3 py-2.5 border-b border-[rgba(0,0,0,0.06)]">
                <p className="text-sm font-semibold text-[#111118]">{displayUser.name}</p>
                <p className="text-xs text-[#6b6b80]">{displayUser.email}</p>
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
                  type="button"
                  onClick={() => void handleLogout()}
                  className="w-full flex items-center gap-2.5 px-3 py-2 text-sm text-[#dc2626] hover:bg-[#fef2f2]"
                >
                  <LogOut className="w-4 h-4" /> 로그아웃
                </button>
              </div>
            </div>
          )}
        </div>
      </div>

      {createWsOpen && (
        <div className="fixed inset-0 bg-black/30 z-50 flex items-center justify-center p-4">
          <div className="bg-white rounded-2xl border border-[rgba(0,0,0,0.08)] shadow-xl w-full max-w-md p-6">
            <h3 className="text-base font-bold text-[#111118] mb-4">새 팀 작업공간</h3>
            <input
              type="text"
              value={newWsName}
              onChange={(e) => setNewWsName(e.target.value)}
              placeholder="작업공간 이름"
              className="w-full h-9 rounded-lg border border-[rgba(0,0,0,0.1)] px-3 text-sm mb-4 focus:outline-none focus:ring-2 focus:ring-[#4f46e5]/20"
            />
            <div className="flex gap-2">
              <Button variant="ghost" className="flex-1" onClick={() => setCreateWsOpen(false)}>취소</Button>
              <Button
                variant="primary"
                className="flex-1"
                loading={creatingWs}
                disabled={creatingWs || !newWsName.trim()}
                onClick={() => void handleCreateWorkspace()}
              >
                만들기
              </Button>
            </div>
          </div>
        </div>
      )}
    </header>
  );
}
