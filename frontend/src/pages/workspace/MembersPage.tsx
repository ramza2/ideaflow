import { useState } from "react";
import { clsx } from "clsx";
import { UserPlus, MoreHorizontal, Mail, Search } from "lucide-react";
import { MOCK_MEMBERS } from "../../mocks/members";
import { MOCK_USERS, getUserById } from "../../mocks/users";
import { Button } from "../../components/common/Button";
import { Input } from "../../components/common/Input";
import { Avatar } from "../../components/common/Avatar";
import { MemberStatusBadge, MemberRoleBadge } from "../../components/common/Badge";

const ROLE_LABELS = {
  admin: "작업공간 관리자",
  member: "일반 구성원",
  readonly: "읽기 전용",
};

export function MembersPage() {
  const [showInviteModal, setShowInviteModal] = useState(false);
  const [inviteEmail, setInviteEmail] = useState("");
  const [inviteRole, setInviteRole] = useState("member");
  const [search, setSearch] = useState("");

  const members = MOCK_MEMBERS.map((m) => ({
    ...m,
    user: getUserById(m.userId),
  })).filter(Boolean);

  const filtered = members.filter((m) =>
    !search || m.user?.name.includes(search) || m.user?.email.includes(search)
  );

  return (
    <div className="flex flex-col h-full">
      {/* Header */}
      <div className="px-4 sm:px-8 pt-6 pb-4 bg-white border-b border-[rgba(0,0,0,0.06)]">
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-xl font-bold text-[#111118]">구성원</h1>
            <p className="text-sm text-[#6b6b80]">IdeaFlow Team · {MOCK_MEMBERS.length}명</p>
          </div>
          <Button
            variant="primary"
            size="sm"
            icon={<UserPlus className="w-3.5 h-3.5" />}
            onClick={() => setShowInviteModal(true)}
          >
            구성원 초대
          </Button>
        </div>
      </div>

      {/* Search */}
      <div className="px-4 sm:px-8 py-3 bg-white border-b border-[rgba(0,0,0,0.05)]">
        <div className="relative max-w-xs">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-[#9ca3af]" />
          <input
            type="text"
            placeholder="구성원 검색..."
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className="w-full h-8 pl-8 pr-3 rounded-lg border border-[rgba(0,0,0,0.1)] bg-[#f4f4f8] text-sm placeholder:text-[#9ca3af] focus:outline-none focus:bg-white focus:border-[rgba(0,0,0,0.15)]"
          />
        </div>
      </div>

      {/* Table */}
      <div className="flex-1 overflow-y-auto px-4 sm:px-8 py-5">
        <div className="overflow-x-auto">
        <div className="bg-white rounded-xl border border-[rgba(0,0,0,0.07)] overflow-hidden min-w-[720px]">
          {/* Table header */}
          <div className="grid grid-cols-[1fr_180px_120px_90px_120px_100px_36px] gap-4 px-4 py-2.5 border-b border-[rgba(0,0,0,0.06)] bg-[#f8f8fb]">
            {["사용자", "이메일", "역할", "상태", "참여일", "최근 활동", ""].map((h, i) => (
              <span key={i} className="text-xs font-medium text-[#6b6b80]">{h}</span>
            ))}
          </div>

          {filtered.map((m) => {
            if (!m.user) return null;
            return (
              <div
                key={m.userId}
                className="grid grid-cols-[1fr_180px_120px_90px_120px_100px_36px] gap-4 px-4 py-3.5 border-b border-[rgba(0,0,0,0.04)] items-center hover:bg-[#f8f8fb] group transition-colors"
              >
                <div className="flex items-center gap-3 min-w-0">
                  <Avatar user={m.user} size="sm" />
                  <div className="min-w-0">
                    <p className="text-sm font-medium text-[#111118] truncate">{m.user.name}</p>
                    {m.userId === "u-001" && (
                      <span className="text-[10px] text-[#4f46e5]">나</span>
                    )}
                  </div>
                </div>
                <span className="text-sm text-[#6b6b80] truncate">{m.user.email}</span>
                <MemberRoleBadge role={m.role} />
                <MemberStatusBadge status={m.status} />
                <span className="text-sm text-[#9ca3af]">{m.joinedAt}</span>
                <span className="text-sm text-[#9ca3af]">{m.lastActiveAt}</span>
                <button className="w-7 h-7 flex items-center justify-center rounded-md text-[#9ca3af] hover:text-[#6b6b80] hover:bg-[#f0f0f5] opacity-0 group-hover:opacity-100 transition-all">
                  <MoreHorizontal className="w-4 h-4" />
                </button>
              </div>
            );
          })}
        </div>
        </div>
      </div>

      {/* Invite modal */}
      {showInviteModal && (
        <div className="fixed inset-0 bg-black/30 z-50 flex items-center justify-center p-4">
          <div className="bg-white rounded-2xl border border-[rgba(0,0,0,0.08)] shadow-xl w-full max-w-md p-6">
            <div className="flex items-center gap-2 mb-5">
              <UserPlus className="w-5 h-5 text-[#4f46e5]" />
              <h3 className="text-base font-bold text-[#111118]">구성원 초대</h3>
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
                    placeholder="email@example.com, email2@example.com"
                    className="flex-1 h-9 rounded-lg border border-[rgba(0,0,0,0.1)] bg-white px-3 text-sm focus:outline-none focus:ring-2 focus:ring-[#4f46e5]/20 focus:border-[#4f46e5]"
                  />
                </div>
                <p className="text-xs text-[#9ca3af] mt-1">여러 이메일을 쉼표로 구분해 입력하세요</p>
              </div>
              <div>
                <label className="text-sm font-medium text-[#111118] block mb-1.5">역할</label>
                <select
                  value={inviteRole}
                  onChange={(e) => setInviteRole(e.target.value)}
                  className="w-full h-9 rounded-lg border border-[rgba(0,0,0,0.1)] bg-white px-3 text-sm focus:outline-none focus:ring-2 focus:ring-[#4f46e5]/20 focus:border-[#4f46e5]"
                >
                  <option value="admin">작업공간 관리자</option>
                  <option value="member">일반 구성원</option>
                  <option value="readonly">읽기 전용</option>
                </select>
              </div>
              <div>
                <label className="text-sm font-medium text-[#111118] block mb-1.5">초대 메시지 (선택)</label>
                <textarea
                  className="w-full h-20 rounded-lg border border-[rgba(0,0,0,0.1)] bg-white px-3 py-2 text-sm resize-none focus:outline-none focus:ring-2 focus:ring-[#4f46e5]/20 focus:border-[#4f46e5]"
                  placeholder="간단한 안내 메시지를 작성하세요"
                />
              </div>
            </div>
            <div className="flex gap-2 mt-5">
              <Button variant="ghost" className="flex-1" onClick={() => setShowInviteModal(false)}>취소</Button>
              <Button variant="primary" className="flex-1" icon={<Mail className="w-3.5 h-3.5" />}>
                초대 보내기
              </Button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
