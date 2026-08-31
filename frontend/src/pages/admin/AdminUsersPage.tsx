import { useCallback, useEffect, useRef, useState } from "react";
import { Search, MoreHorizontal, UserPlus, KeyRound, Unlock } from "lucide-react";
import { AdminShell } from "../../components/admin/AdminShell";
import { Button } from "../../components/common/Button";
import { EmptyState, InlineAlert } from "../../components/common/EmptyState";
import { toast } from "../../components/common/Toast";
import {
  createAdminUser,
  listAdminUsers,
  resetAdminUserPassword,
  unlockAdminUserLogin,
  updateAdminUser,
} from "../../api/adminUsers";
import { apiErrorMessage } from "../../api/client";
import type { AdminUserPublic, SystemRole, UserStatus } from "../../types/api";

type StatusFilter = "" | UserStatus;
type RoleFilter = "" | SystemRole;

function formatDate(value: string | null): string {
  if (!value) return "-";
  return new Date(value).toLocaleString("ko-KR");
}

function statusLabel(status: UserStatus): string {
  switch (status) {
    case "ACTIVE":
      return "활성";
    case "INACTIVE":
      return "비활성";
    case "LOCKED":
      return "잠금";
    case "WITHDRAWN":
      return "탈퇴";
    default:
      return status;
  }
}

function roleLabel(role: SystemRole): string {
  return role === "SYSTEM_ADMIN" ? "시스템 관리자" : "일반 사용자";
}

export function AdminUsersPage() {
  const [items, setItems] = useState<AdminUserPublic[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [q, setQ] = useState("");
  const [statusFilter, setStatusFilter] = useState<StatusFilter>("");
  const [roleFilter, setRoleFilter] = useState<RoleFilter>("");
  const [menuUserId, setMenuUserId] = useState<string | null>(null);
  const requestGen = useRef(0);

  const [createOpen, setCreateOpen] = useState(false);
  const [createName, setCreateName] = useState("");
  const [createEmail, setCreateEmail] = useState("");
  const [createPassword, setCreatePassword] = useState("");
  const [createRole, setCreateRole] = useState<SystemRole>("USER");
  const [creating, setCreating] = useState(false);

  const [resetUserId, setResetUserId] = useState<string | null>(null);
  const [resetPassword, setResetPassword] = useState("");
  const [resetting, setResetting] = useState(false);

  const loadUsers = useCallback(async () => {
    const gen = ++requestGen.current;
    setLoading(true);
    setError(null);
    try {
      const data = await listAdminUsers({
        q: q.trim() || undefined,
        status: statusFilter || undefined,
        system_role: roleFilter || undefined,
        limit: 50,
      });
      if (gen !== requestGen.current) return;
      setItems(data.items);
      setTotal(data.total);
    } catch (err) {
      if (gen !== requestGen.current) return;
      setError(apiErrorMessage(err, "사용자 목록을 불러오지 못했습니다."));
      setItems([]);
      setTotal(0);
    } finally {
      if (gen === requestGen.current) setLoading(false);
    }
  }, [q, statusFilter, roleFilter]);

  useEffect(() => {
    void loadUsers();
  }, [loadUsers]);

  async function handleCreate() {
    if (!createName.trim() || !createEmail.trim() || !createPassword) return;
    setCreating(true);
    try {
      await createAdminUser({
        name: createName.trim(),
        email: createEmail.trim(),
        temporary_password: createPassword,
        system_role: createRole,
      });
      toast.success("사용자가 생성되었습니다.");
      setCreateOpen(false);
      setCreateName("");
      setCreateEmail("");
      setCreatePassword("");
      setCreateRole("USER");
      await loadUsers();
    } catch (err) {
      toast.error(apiErrorMessage(err, "사용자 생성에 실패했습니다."));
    } finally {
      setCreating(false);
    }
  }

  async function handleStatusChange(target: AdminUserPublic, status: UserStatus) {
    if (!window.confirm(`이 사용자의 상태를 '${statusLabel(status)}'(으)로 변경하시겠습니까?`)) return;
    try {
      await updateAdminUser(target.id, { status });
      toast.success("상태가 변경되었습니다.");
      await loadUsers();
    } catch (err) {
      toast.error(apiErrorMessage(err, "상태 변경에 실패했습니다."));
    } finally {
      setMenuUserId(null);
    }
  }

  async function handleRoleChange(target: AdminUserPublic, system_role: SystemRole) {
    if (!window.confirm(`시스템 역할을 '${roleLabel(system_role)}'(으)로 변경하시겠습니까?`)) return;
    try {
      await updateAdminUser(target.id, { system_role });
      toast.success("역할이 변경되었습니다.");
      await loadUsers();
    } catch (err) {
      toast.error(apiErrorMessage(err, "역할 변경에 실패했습니다."));
    } finally {
      setMenuUserId(null);
    }
  }

  async function handleUnlock(target: AdminUserPublic) {
    try {
      await unlockAdminUserLogin(target.id);
      toast.success("로그인 임시 잠금이 해제되었습니다.");
      await loadUsers();
    } catch (err) {
      toast.error(apiErrorMessage(err, "잠금 해제에 실패했습니다."));
    } finally {
      setMenuUserId(null);
    }
  }

  async function handleResetPassword() {
    if (!resetUserId || !resetPassword) return;
    if (!window.confirm("임시 비밀번호를 재설정하시겠습니까? 기존 세션이 모두 종료됩니다.")) return;
    setResetting(true);
    try {
      await resetAdminUserPassword(resetUserId, { temporary_password: resetPassword });
      toast.success("임시 비밀번호가 설정되었습니다.");
      setResetUserId(null);
      setResetPassword("");
      await loadUsers();
    } catch (err) {
      toast.error(apiErrorMessage(err, "비밀번호 재설정에 실패했습니다."));
    } finally {
      setResetting(false);
    }
  }

  return (
    <AdminShell title="사용자 관리">
      <div className="px-4 sm:px-8 py-6 space-y-4">
        <div className="flex flex-col sm:flex-row sm:items-center gap-3 justify-between">
          <div className="flex flex-wrap gap-2 flex-1">
            <div className="relative flex-1 min-w-[200px] max-w-md">
              <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-[#9ca3af]" />
              <input
                value={q}
                onChange={(e) => setQ(e.target.value)}
                placeholder="이름 또는 이메일 검색"
                className="w-full h-9 pl-9 pr-3 rounded-lg border border-[rgba(0,0,0,0.1)] bg-white text-sm"
              />
            </div>
            <select
              value={statusFilter}
              onChange={(e) => setStatusFilter(e.target.value as StatusFilter)}
              className="h-9 rounded-lg border border-[rgba(0,0,0,0.1)] bg-white px-3 text-sm"
            >
              <option value="">모든 상태</option>
              <option value="ACTIVE">활성</option>
              <option value="INACTIVE">비활성</option>
              <option value="LOCKED">잠금</option>
              <option value="WITHDRAWN">탈퇴</option>
            </select>
            <select
              value={roleFilter}
              onChange={(e) => setRoleFilter(e.target.value as RoleFilter)}
              className="h-9 rounded-lg border border-[rgba(0,0,0,0.1)] bg-white px-3 text-sm"
            >
              <option value="">모든 역할</option>
              <option value="USER">일반 사용자</option>
              <option value="SYSTEM_ADMIN">시스템 관리자</option>
            </select>
          </div>
          <Button variant="primary" icon={<UserPlus className="w-4 h-4" />} onClick={() => setCreateOpen(true)}>
            사용자 생성
          </Button>
        </div>

        {error && <InlineAlert type="error" title="오류">{error}</InlineAlert>}

        <div className="bg-white rounded-xl border border-[rgba(0,0,0,0.07)] overflow-hidden">
          {loading ? (
            <div className="p-8 text-center text-sm text-[#6b6b80]">불러오는 중...</div>
          ) : items.length === 0 ? (
            <EmptyState title="사용자 없음" description="조건에 맞는 사용자가 없습니다." />
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead className="bg-[#f8f8fb] text-[#6b6b80]">
                  <tr>
                    <th className="text-left px-4 py-3 font-medium">사용자</th>
                    <th className="text-left px-4 py-3 font-medium">역할</th>
                    <th className="text-left px-4 py-3 font-medium">상태</th>
                    <th className="text-left px-4 py-3 font-medium">로그인</th>
                    <th className="text-left px-4 py-3 font-medium">세션</th>
                    <th className="text-left px-4 py-3 font-medium">최근 활동</th>
                    <th className="text-left px-4 py-3 font-medium">생성일</th>
                    <th className="px-4 py-3" />
                  </tr>
                </thead>
                <tbody>
                  {items.map((u) => (
                    <tr key={u.id} className="border-t border-[rgba(0,0,0,0.06)]">
                      <td className="px-4 py-3">
                        <p className="font-medium text-[#111118]">{u.name}</p>
                        <p className="text-xs text-[#6b6b80]">{u.email}</p>
                      </td>
                      <td className="px-4 py-3">{roleLabel(u.system_role)}</td>
                      <td className="px-4 py-3">{statusLabel(u.status)}</td>
                      <td className="px-4 py-3">
                        {u.temporary_login_locked ? (
                          <span className="text-xs text-[#d97706]">
                            로그인 잠금
                            {u.locked_until ? ` · ${formatDate(u.locked_until)}까지` : ""}
                          </span>
                        ) : (
                          <span className="text-xs text-[#16a34a]">정상</span>
                        )}
                      </td>
                      <td className="px-4 py-3">{u.active_session_count}</td>
                      <td className="px-4 py-3 text-xs text-[#6b6b80]">{formatDate(u.last_seen_at)}</td>
                      <td className="px-4 py-3 text-xs text-[#6b6b80]">{formatDate(u.created_at)}</td>
                      <td className="px-4 py-3 relative">
                        {u.status !== "WITHDRAWN" && (
                          <>
                            <button
                              type="button"
                              onClick={() => setMenuUserId(menuUserId === u.id ? null : u.id)}
                              className="p-1.5 rounded-lg hover:bg-[#f4f4f8]"
                            >
                              <MoreHorizontal className="w-4 h-4 text-[#6b6b80]" />
                            </button>
                            {menuUserId === u.id && (
                              <div className="absolute right-4 top-10 z-20 w-48 bg-white rounded-xl border border-[rgba(0,0,0,0.08)] shadow-lg py-1">
                                {u.status !== "ACTIVE" && !u.is_current_user && (
                                  <button
                                    className="w-full text-left px-3 py-2 text-sm hover:bg-[#f4f4f8]"
                                    onClick={() => void handleStatusChange(u, "ACTIVE")}
                                  >
                                    활성화
                                  </button>
                                )}
                                {u.status === "ACTIVE" && !u.is_current_user && (
                                  <>
                                    <button
                                      className="w-full text-left px-3 py-2 text-sm hover:bg-[#f4f4f8]"
                                      onClick={() => void handleStatusChange(u, "INACTIVE")}
                                    >
                                      비활성화
                                    </button>
                                    <button
                                      className="w-full text-left px-3 py-2 text-sm hover:bg-[#f4f4f8]"
                                      onClick={() => void handleStatusChange(u, "LOCKED")}
                                    >
                                      계정 잠금
                                    </button>
                                  </>
                                )}
                                {u.system_role === "USER" && !u.is_current_user && (
                                  <button
                                    className="w-full text-left px-3 py-2 text-sm hover:bg-[#f4f4f8]"
                                    onClick={() => void handleRoleChange(u, "SYSTEM_ADMIN")}
                                  >
                                    시스템 관리자 지정
                                  </button>
                                )}
                                {u.system_role === "SYSTEM_ADMIN" && !u.is_current_user && (
                                  <button
                                    className="w-full text-left px-3 py-2 text-sm hover:bg-[#f4f4f8]"
                                    onClick={() => void handleRoleChange(u, "USER")}
                                  >
                                    일반 사용자로 변경
                                  </button>
                                )}
                                {u.temporary_login_locked && (
                                  <button
                                    className="w-full text-left px-3 py-2 text-sm hover:bg-[#f4f4f8] flex items-center gap-2"
                                    onClick={() => void handleUnlock(u)}
                                  >
                                    <Unlock className="w-3.5 h-3.5" /> 로그인 잠금 해제
                                  </button>
                                )}
                                {!u.is_current_user && (
                                  <button
                                    className="w-full text-left px-3 py-2 text-sm hover:bg-[#f4f4f8] flex items-center gap-2"
                                    onClick={() => {
                                      setResetUserId(u.id);
                                      setResetPassword("");
                                      setMenuUserId(null);
                                    }}
                                  >
                                    <KeyRound className="w-3.5 h-3.5" /> 임시 비밀번호 재설정
                                  </button>
                                )}
                              </div>
                            )}
                          </>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
          {!loading && total > 0 && (
            <div className="px-4 py-3 border-t border-[rgba(0,0,0,0.06)] text-xs text-[#6b6b80]">
              총 {total}명
            </div>
          )}
        </div>
      </div>

      {createOpen && (
        <div className="fixed inset-0 bg-black/30 z-50 flex items-center justify-center p-4">
          <div className="bg-white rounded-2xl border border-[rgba(0,0,0,0.08)] shadow-xl w-full max-w-md p-6 space-y-4">
            <h3 className="text-base font-bold text-[#111118]">사용자 생성</h3>
            <input
              value={createName}
              onChange={(e) => setCreateName(e.target.value)}
              placeholder="이름"
              className="w-full h-9 rounded-lg border border-[rgba(0,0,0,0.1)] px-3 text-sm"
            />
            <input
              type="email"
              value={createEmail}
              onChange={(e) => setCreateEmail(e.target.value)}
              placeholder="이메일"
              className="w-full h-9 rounded-lg border border-[rgba(0,0,0,0.1)] px-3 text-sm"
            />
            <input
              type="password"
              value={createPassword}
              onChange={(e) => setCreatePassword(e.target.value)}
              placeholder="임시 비밀번호 (10자 이상)"
              className="w-full h-9 rounded-lg border border-[rgba(0,0,0,0.1)] px-3 text-sm"
            />
            <select
              value={createRole}
              onChange={(e) => setCreateRole(e.target.value as SystemRole)}
              className="w-full h-9 rounded-lg border border-[rgba(0,0,0,0.1)] px-3 text-sm"
            >
              <option value="USER">일반 사용자</option>
              <option value="SYSTEM_ADMIN">시스템 관리자</option>
            </select>
            <div className="flex justify-end gap-2 pt-2">
              <Button variant="secondary" onClick={() => setCreateOpen(false)}>취소</Button>
              <Button variant="primary" loading={creating} onClick={() => void handleCreate()}>
                생성
              </Button>
            </div>
          </div>
        </div>
      )}

      {resetUserId && (
        <div className="fixed inset-0 bg-black/30 z-50 flex items-center justify-center p-4">
          <div className="bg-white rounded-2xl border border-[rgba(0,0,0,0.08)] shadow-xl w-full max-w-md p-6 space-y-4">
            <h3 className="text-base font-bold text-[#111118]">임시 비밀번호 재설정</h3>
            <input
              type="password"
              value={resetPassword}
              onChange={(e) => setResetPassword(e.target.value)}
              placeholder="새 임시 비밀번호 (10자 이상)"
              className="w-full h-9 rounded-lg border border-[rgba(0,0,0,0.1)] px-3 text-sm"
            />
            <div className="flex justify-end gap-2 pt-2">
              <Button variant="secondary" onClick={() => setResetUserId(null)}>취소</Button>
              <Button variant="primary" loading={resetting} onClick={() => void handleResetPassword()}>
                재설정
              </Button>
            </div>
          </div>
        </div>
      )}
    </AdminShell>
  );
}
