import { useEffect, useState } from "react";
import { UserPlus, MoreHorizontal, Mail, Search } from "lucide-react";
import {
  addMember,
  deactivateMember,
  listMembers,
  updateMemberRole,
} from "../../api/workspaces";
import { apiErrorMessage } from "../../api/client";
import { useAuth } from "../../auth/AuthProvider";
import { useWorkspace } from "../../workspace/WorkspaceProvider";
import { Button } from "../../components/common/Button";
import { Avatar } from "../../components/common/Avatar";
import { ApiMemberRoleBadge, ApiMemberStatusBadge } from "../../components/common/Badge";
import { EmptyState } from "../../components/common/EmptyState";
import { toast } from "../../components/common/Toast";
import { WorkspaceSettingsNav } from "../../components/workspace/WorkspaceSettingsNav";
import { toDisplayUser } from "../../utils/avatar";
import type { MemberPublic, WorkspaceRole } from "../../types/api";

export function MembersPage() {
  const { user } = useAuth();
  const { currentWorkspace } = useWorkspace();
  const workspaceId = currentWorkspace?.id ?? "";

  const [members, setMembers] = useState<MemberPublic[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [showInviteModal, setShowInviteModal] = useState(false);
  const [inviteEmail, setInviteEmail] = useState("");
  const [inviteRole, setInviteRole] = useState<WorkspaceRole>("MEMBER");
  const [submitting, setSubmitting] = useState(false);
  const [search, setSearch] = useState("");
  const [menuUserId, setMenuUserId] = useState<string | null>(null);

  const isAdmin = currentWorkspace?.current_user_role === "ADMIN";
  const isPersonal = currentWorkspace?.type === "PERSONAL";
  const canManage = isAdmin && !isPersonal;

  async function loadMembers() {
    if (!workspaceId) return;
    setLoading(true);
    setError(null);
    try {
      const data = await listMembers(workspaceId);
      setMembers(data);
    } catch (err) {
      setError(apiErrorMessage(err));
      setMembers([]);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    void loadMembers();
  }, [workspaceId]); // eslint-disable-line react-hooks/exhaustive-deps

  const filtered = members.filter(
    (m) => !search || m.name.includes(search) || m.email.includes(search),
  );

  async function handleAddMember() {
    if (!workspaceId || !inviteEmail.trim()) return;
    setSubmitting(true);
    try {
      await addMember(workspaceId, { email: inviteEmail.trim(), role: inviteRole });
      toast.success("멤버가 추가되었습니다.");
      setShowInviteModal(false);
      setInviteEmail("");
      await loadMembers();
    } catch (err) {
      toast.error(apiErrorMessage(err, "멤버 추가에 실패했습니다."));
    } finally {
      setSubmitting(false);
    }
  }

  async function handleRoleChange(userId: string, role: WorkspaceRole) {
    if (!workspaceId) return;
    try {
      await updateMemberRole(workspaceId, userId, { role });
      toast.success("역할이 변경되었습니다.");
      setMenuUserId(null);
      await loadMembers();
    } catch (err) {
      toast.error(apiErrorMessage(err));
    }
  }

  async function handleDeactivate(userId: string) {
    if (!workspaceId) return;
    try {
      await deactivateMember(workspaceId, userId);
      toast.success("멤버가 비활성화되었습니다.");
      setMenuUserId(null);
      await loadMembers();
    } catch (err) {
      toast.error(apiErrorMessage(err));
    }
  }

  return (
    <div className="flex flex-col h-full">
      <WorkspaceSettingsNav />
      <div className="px-4 sm:px-8 py-3 bg-white border-b border-[rgba(0,0,0,0.05)] flex flex-col sm:flex-row sm:items-center gap-3 justify-between">
        <div className="relative max-w-xs w-full">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-[#9ca3af]" />
          <input
            type="text"
            placeholder="구성원 검색..."
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className="w-full h-8 pl-8 pr-3 rounded-lg border border-[rgba(0,0,0,0.1)] bg-[#f4f4f8] text-sm placeholder:text-[#9ca3af] focus:outline-none focus:bg-white focus:border-[rgba(0,0,0,0.15)]"
          />
        </div>
        {canManage && (
          <Button
            variant="primary"
            size="sm"
            icon={<UserPlus className="w-3.5 h-3.5" />}
            onClick={() => setShowInviteModal(true)}
          >
            구성원 추가
          </Button>
        )}
      </div>

      <div className="flex-1 overflow-y-auto px-4 sm:px-8 py-5">
        {loading ? (
          <div className="py-12 text-center text-sm text-[#6b6b80]">불러오는 중...</div>
        ) : error ? (
          <EmptyState title="구성원을 불러올 수 없습니다" description={error} />
        ) : filtered.length === 0 ? (
          <EmptyState title="구성원이 없습니다" description="팀 작업공간에 구성원을 추가해 보세요." />
        ) : (
          <div className="overflow-x-auto">
            <div className="bg-white rounded-xl border border-[rgba(0,0,0,0.07)] overflow-hidden min-w-[720px]">
              <div className="grid grid-cols-[1fr_180px_120px_90px_120px_36px] gap-4 px-4 py-2.5 border-b border-[rgba(0,0,0,0.06)] bg-[#f8f8fb]">
                {["사용자", "이메일", "역할", "상태", "참여일", ""].map((h, i) => (
                  <span key={i} className="text-xs font-medium text-[#6b6b80]">{h}</span>
                ))}
              </div>

              {filtered.map((m) => {
                const display = toDisplayUser({ id: m.user_id, name: m.name, email: m.email });
                return (
                  <div
                    key={m.user_id}
                    className="grid grid-cols-[1fr_180px_120px_90px_120px_36px] gap-4 px-4 py-3.5 border-b border-[rgba(0,0,0,0.04)] items-center hover:bg-[#f8f8fb] group transition-colors relative"
                  >
                    <div className="flex items-center gap-3 min-w-0">
                      <Avatar user={display} size="sm" />
                      <div className="min-w-0">
                        <p className="text-sm font-medium text-[#111118] truncate">{m.name}</p>
                        {user?.id === m.user_id && (
                          <span className="text-[10px] text-[#4f46e5]">나</span>
                        )}
                      </div>
                    </div>
                    <span className="text-sm text-[#6b6b80] truncate">{m.email}</span>
                    <ApiMemberRoleBadge role={m.role} />
                    <ApiMemberStatusBadge status={m.status} />
                    <span className="text-sm text-[#9ca3af]">
                      {new Date(m.created_at).toLocaleDateString("ko")}
                    </span>
                    {canManage && m.user_id !== user?.id && m.status === "ACTIVE" && (
                      <div className="relative">
                        <button
                          type="button"
                          onClick={() => setMenuUserId(menuUserId === m.user_id ? null : m.user_id)}
                          className="w-7 h-7 flex items-center justify-center rounded-md text-[#9ca3af] hover:text-[#6b6b80] hover:bg-[#f0f0f5] opacity-0 group-hover:opacity-100 transition-all"
                        >
                          <MoreHorizontal className="w-4 h-4" />
                        </button>
                        {menuUserId === m.user_id && (
                          <div className="absolute right-0 top-full mt-1 w-40 bg-white rounded-lg border border-[rgba(0,0,0,0.08)] shadow-lg py-1 z-10">
                            {(["ADMIN", "MEMBER", "VIEWER"] as WorkspaceRole[]).map((role) => (
                              <button
                                key={role}
                                type="button"
                                onClick={() => void handleRoleChange(m.user_id, role)}
                                className="w-full text-left px-3 py-2 text-xs hover:bg-[#f4f4f8]"
                              >
                                {role === "ADMIN" ? "관리자로" : role === "MEMBER" ? "멤버로" : "읽기 전용으로"}
                              </button>
                            ))}
                            <button
                              type="button"
                              onClick={() => void handleDeactivate(m.user_id)}
                              className="w-full text-left px-3 py-2 text-xs text-[#dc2626] hover:bg-[#fef2f2]"
                            >
                              비활성화
                            </button>
                          </div>
                        )}
                      </div>
                    )}
                  </div>
                );
              })}
            </div>
          </div>
        )}
      </div>

      {showInviteModal && (
        <div className="fixed inset-0 bg-black/30 z-50 flex items-center justify-center p-4">
          <div className="bg-white rounded-2xl border border-[rgba(0,0,0,0.08)] shadow-xl w-full max-w-md p-6">
            <div className="flex items-center gap-2 mb-5">
              <UserPlus className="w-5 h-5 text-[#4f46e5]" />
              <h3 className="text-base font-bold text-[#111118]">구성원 추가</h3>
            </div>
            <div className="space-y-4">
              <div>
                <label className="text-sm font-medium text-[#111118] block mb-1.5">이메일 주소</label>
                <div className="flex items-center gap-1.5">
                  <Mail className="w-4 h-4 text-[#9ca3af]" />
                  <input
                    type="email"
                    value={inviteEmail}
                    onChange={(e) => setInviteEmail(e.target.value)}
                    placeholder="email@example.com"
                    className="flex-1 h-9 rounded-lg border border-[rgba(0,0,0,0.1)] bg-white px-3 text-sm focus:outline-none focus:ring-2 focus:ring-[#4f46e5]/20 focus:border-[#4f46e5]"
                  />
                </div>
                <p className="text-xs text-[#9ca3af] mt-1">기존 IdeaFlow 사용자 이메일을 입력하세요</p>
              </div>
              <div>
                <label className="text-sm font-medium text-[#111118] block mb-1.5">역할</label>
                <select
                  value={inviteRole}
                  onChange={(e) => setInviteRole(e.target.value as WorkspaceRole)}
                  className="w-full h-9 rounded-lg border border-[rgba(0,0,0,0.1)] bg-white px-3 text-sm focus:outline-none focus:ring-2 focus:ring-[#4f46e5]/20 focus:border-[#4f46e5]"
                >
                  <option value="ADMIN">작업공간 관리자</option>
                  <option value="MEMBER">일반 구성원</option>
                  <option value="VIEWER">읽기 전용</option>
                </select>
              </div>
            </div>
            <div className="flex gap-2 mt-5">
              <Button variant="ghost" className="flex-1" onClick={() => setShowInviteModal(false)}>취소</Button>
              <Button
                variant="primary"
                className="flex-1"
                loading={submitting}
                disabled={submitting || !inviteEmail.trim()}
                onClick={() => void handleAddMember()}
              >
                추가
              </Button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
