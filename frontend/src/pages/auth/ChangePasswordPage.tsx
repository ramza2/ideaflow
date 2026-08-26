import { useState } from "react";
import { useNavigate } from "react-router";
import { Eye, EyeOff, Lightbulb, Sparkles, ArrowRight } from "lucide-react";
import { Button } from "../../components/common/Button";
import { Input } from "../../components/common/Input";
import * as authApi from "../../api/auth";
import { ApiError } from "../../api/client";
import { useAuth } from "../../auth/AuthProvider";

export function ChangePasswordPage() {
  const navigate = useNavigate();
  const { refreshUser } = useAuth();
  const [currentPassword, setCurrentPassword] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [showPw, setShowPw] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);

    if (newPassword.length < 10) {
      setError("새 비밀번호는 10자 이상이어야 합니다.");
      return;
    }
    if (newPassword !== confirmPassword) {
      setError("새 비밀번호가 일치하지 않습니다.");
      return;
    }

    setSubmitting(true);
    try {
      await authApi.changePassword(currentPassword, newPassword);
      await refreshUser();
      navigate("/w/personal/home", { replace: true });
    } catch (err) {
      if (err instanceof ApiError) {
        setError(err.message);
      } else {
        setError("비밀번호 변경에 실패했습니다.");
      }
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="min-h-screen flex items-center justify-center p-8 bg-[#f8f8f9]">
      <div className="w-full max-w-sm">
        <div className="flex items-center gap-2 mb-8">
          <div className="w-7 h-7 rounded-lg bg-[#4f46e5] flex items-center justify-center">
            <Lightbulb className="w-4 h-4 text-white" />
          </div>
          <span className="text-base font-bold text-[#111118]">IdeaFlow</span>
        </div>

        <div className="bg-white rounded-2xl border border-[rgba(0,0,0,0.08)] p-8 shadow-sm">
          <div className="flex items-center gap-2 mb-1">
            <Sparkles className="w-4 h-4 text-[#7c3aed]" />
            <h1 className="text-xl font-bold text-[#111118]">비밀번호 변경</h1>
          </div>
          <p className="text-sm text-[#6b6b80] mb-6">
            보안을 위해 비밀번호를 변경한 후 서비스를 이용할 수 있습니다.
          </p>

          {error && (
            <div className="mb-4 p-3 rounded-lg bg-[#fef2f2] border border-[#fecaca] text-sm text-[#b91c1c]">
              {error}
            </div>
          )}

          <form onSubmit={handleSubmit} className="space-y-4">
            <Input
              label="현재 비밀번호"
              type={showPw ? "text" : "password"}
              value={currentPassword}
              onChange={(e) => setCurrentPassword(e.target.value)}
              required
            />
            <Input
              label="새 비밀번호"
              type={showPw ? "text" : "password"}
              value={newPassword}
              onChange={(e) => setNewPassword(e.target.value)}
              placeholder="10자 이상"
              required
            />
            <div className="flex flex-col gap-1.5">
              <label className="text-sm font-medium text-[#111118]">새 비밀번호 확인</label>
              <div className="relative">
                <input
                  type={showPw ? "text" : "password"}
                  value={confirmPassword}
                  onChange={(e) => setConfirmPassword(e.target.value)}
                  className="w-full h-9 rounded-lg border border-[rgba(0,0,0,0.1)] bg-white px-3 pr-10 text-sm focus:outline-none focus:ring-2 focus:ring-[#4f46e5]/20 focus:border-[#4f46e5]"
                  required
                />
                <button
                  type="button"
                  onClick={() => setShowPw(!showPw)}
                  className="absolute right-3 top-1/2 -translate-y-1/2 text-[#9ca3af]"
                >
                  {showPw ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
                </button>
              </div>
            </div>

            <Button
              type="submit"
              variant="primary"
              size="lg"
              loading={submitting}
              className="w-full"
              icon={<ArrowRight className="w-4 h-4" />}
            >
              비밀번호 변경
            </Button>
          </form>
        </div>
      </div>
    </div>
  );
}
