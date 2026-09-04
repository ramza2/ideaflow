import { useNavigate } from "react-router";
import { Button } from "../../components/common/Button";
import { UserSettingsNav } from "../../components/settings/UserSettingsNav";

export function SecuritySettingsPage() {
  const navigate = useNavigate();

  return (
    <div className="flex-1 overflow-y-auto bg-[#f8f8fb]">
      <UserSettingsNav />
      <div className="max-w-xl mx-auto px-4 sm:px-8 py-8">
        <div className="bg-white rounded-xl border border-[rgba(0,0,0,0.07)] p-6 space-y-4">
          <div>
            <h2 className="text-base font-bold text-[#111118]">보안</h2>
            <p className="text-sm text-[#6b6b80] mt-1">비밀번호를 변경하려면 기존 변경 화면을 사용합니다.</p>
          </div>
          <div className="flex items-center justify-between gap-4 py-3 border-t border-[rgba(0,0,0,0.06)]">
            <div>
              <p className="text-sm font-medium text-[#111118]">비밀번호</p>
              <p className="text-xs text-[#6b6b80] mt-0.5">현재 계정의 로그인 비밀번호</p>
            </div>
            <Button variant="secondary" onClick={() => navigate("/change-password")}>
              비밀번호 변경
            </Button>
          </div>
        </div>
      </div>
    </div>
  );
}
