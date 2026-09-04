import { useEffect, useState } from "react";
import { useAuth } from "../../auth/AuthProvider";
import { updateMyProfile } from "../../api/auth";
import { apiErrorMessage } from "../../api/client";
import { Button } from "../../components/common/Button";
import { Input } from "../../components/common/Input";
import { InlineAlert } from "../../components/common/EmptyState";
import { toast } from "../../components/common/Toast";
import { UserSettingsNav } from "../../components/settings/UserSettingsNav";

export function ProfileSettingsPage() {
  const { user, refreshUser } = useAuth();
  const [name, setName] = useState(user?.name ?? "");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setName(user?.name ?? "");
  }, [user?.name]);

  async function handleSave(e: React.FormEvent) {
    e.preventDefault();
    const trimmed = name.trim();
    if (!trimmed) {
      setError("이름을 입력해 주세요.");
      return;
    }
    setSaving(true);
    setError(null);
    try {
      await updateMyProfile({ name: trimmed });
      await refreshUser();
      toast.success("프로필을 저장했습니다.");
    } catch (err) {
      setError(apiErrorMessage(err, "프로필을 저장하지 못했습니다."));
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="flex-1 overflow-y-auto bg-[#f8f8fb]">
      <UserSettingsNav />
      <div className="max-w-xl mx-auto px-4 sm:px-8 py-8">
        <form onSubmit={handleSave} className="bg-white rounded-xl border border-[rgba(0,0,0,0.07)] p-6 space-y-5">
          <div>
            <h2 className="text-base font-bold text-[#111118]">프로필</h2>
            <p className="text-sm text-[#6b6b80] mt-1">이름만 수정할 수 있습니다. 이메일과 시스템 역할은 변경할 수 없습니다.</p>
          </div>
          {error && <InlineAlert type="error" title="오류">{error}</InlineAlert>}
          <Input
            label="이름"
            value={name}
            onChange={(e) => setName(e.target.value)}
            maxLength={100}
            required
          />
          <div className="flex flex-col gap-1.5">
            <label className="text-sm font-medium text-[#111118]">이메일</label>
            <input
              value={user?.email ?? ""}
              readOnly
              className="h-9 rounded-lg border border-[rgba(0,0,0,0.1)] bg-[#f8f8fb] px-3 text-sm text-[#6b6b80]"
            />
          </div>
          <div className="flex flex-col gap-1.5">
            <label className="text-sm font-medium text-[#111118]">시스템 역할</label>
            <input
              value={user?.system_role === "SYSTEM_ADMIN" ? "시스템 관리자" : "일반 사용자"}
              readOnly
              className="h-9 rounded-lg border border-[rgba(0,0,0,0.1)] bg-[#f8f8fb] px-3 text-sm text-[#6b6b80]"
            />
          </div>
          <div className="flex flex-col gap-1.5">
            <label className="text-sm font-medium text-[#111118]">계정 상태</label>
            <input
              value={user?.status ?? ""}
              readOnly
              className="h-9 rounded-lg border border-[rgba(0,0,0,0.1)] bg-[#f8f8fb] px-3 text-sm text-[#6b6b80]"
            />
          </div>
          <div className="pt-2">
            <Button type="submit" disabled={saving || name.trim() === (user?.name ?? "")}>
              {saving ? "저장 중..." : "저장"}
            </Button>
          </div>
        </form>
      </div>
    </div>
  );
}
