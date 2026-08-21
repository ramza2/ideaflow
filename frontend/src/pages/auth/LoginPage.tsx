import { useState } from "react";
import { useNavigate } from "react-router";
import { clsx } from "clsx";
import { Eye, EyeOff, Sparkles, ArrowRight, Lightbulb } from "lucide-react";
import { Button } from "../../components/common/Button";
import { Input } from "../../components/common/Input";

type LoginState = "idle" | "loading" | "error" | "inactive" | "expired";

export function LoginPage() {
  const navigate = useNavigate();
  const [email, setEmail] = useState("changhyun@openlink.kr");
  const [password, setPassword] = useState("");
  const [showPw, setShowPw] = useState(false);
  const [remember, setRemember] = useState(false);
  const [status, setStatus] = useState<LoginState>("idle");

  function handleLogin(e: React.FormEvent) {
    e.preventDefault();
    setStatus("loading");
    setTimeout(() => {
      if (password === "wrong") {
        setStatus("error");
      } else {
        setStatus("idle");
        navigate("/w/personal/home");
      }
    }, 1200);
  }

  return (
    <div className="min-h-screen flex">
      {/* Left brand panel */}
      <div className="hidden lg:flex w-1/2 bg-[#111118] text-white flex-col justify-between p-12 relative overflow-hidden">
        {/* Decorative grid */}
        <div
          className="absolute inset-0 opacity-5"
          style={{
            backgroundImage:
              "linear-gradient(rgba(255,255,255,.3) 1px, transparent 1px), linear-gradient(90deg, rgba(255,255,255,.3) 1px, transparent 1px)",
            backgroundSize: "40px 40px",
          }}
        />
        {/* Floating cards illustration */}
        <div className="absolute inset-0 flex items-center justify-center">
          <div className="relative w-80 h-80">
            {[
              { top: "0%", left: "10%", rotate: "-6deg", delay: "0s", label: "AI로 빠르게 정리하기" },
              { top: "25%", left: "35%", rotate: "3deg", delay: "0.2s", label: "구조화 완료 ✓" },
              { top: "50%", left: "5%", rotate: "-3deg", delay: "0.4s", label: "웹 검색으로 보완" },
            ].map((card, i) => (
              <div
                key={i}
                className="absolute bg-white/10 backdrop-blur border border-white/20 rounded-xl px-4 py-2.5 text-sm font-medium text-white/90"
                style={{
                  top: card.top,
                  left: card.left,
                  transform: `rotate(${card.rotate})`,
                  animationDelay: card.delay,
                }}
              >
                {card.label}
              </div>
            ))}
            <div className="absolute bottom-0 right-0 w-16 h-16 rounded-2xl bg-[#4f46e5] flex items-center justify-center">
              <Sparkles className="w-8 h-8 text-white" />
            </div>
          </div>
        </div>

        {/* Logo */}
        <div className="relative flex items-center gap-2.5 z-10">
          <div className="w-8 h-8 rounded-lg bg-[#4f46e5] flex items-center justify-center">
            <Lightbulb className="w-4.5 h-4.5 text-white" />
          </div>
          <span className="text-lg font-bold">IdeaFlow</span>
        </div>

        {/* Tagline */}
        <div className="relative z-10">
          <p className="text-3xl font-bold leading-snug mb-3">
            생각나는 대로 적으세요.
            <br />
            <span className="text-[#818cf8]">IdeaFlow가 구조화하고</span>
            <br />
            발전시킵니다.
          </p>
          <p className="text-white/50 text-sm">
            자연어로 입력하면 AI가 분류하고 팀이 함께 발전시키는 아이디어 관리 플랫폼
          </p>
        </div>
      </div>

      {/* Right login panel */}
      <div className="flex-1 flex items-center justify-center p-8 bg-[#f8f8f9]">
        <div className="w-full max-w-sm">
          {/* Mobile logo */}
          <div className="flex items-center gap-2 mb-8 lg:hidden">
            <div className="w-7 h-7 rounded-lg bg-[#4f46e5] flex items-center justify-center">
              <Lightbulb className="w-4 h-4 text-white" />
            </div>
            <span className="text-base font-bold text-[#111118]">IdeaFlow</span>
          </div>

          <div className="bg-white rounded-2xl border border-[rgba(0,0,0,0.08)] p-8 shadow-sm">
            <h1 className="text-xl font-bold text-[#111118] mb-1.5">IdeaFlow에 로그인</h1>
            <p className="text-sm text-[#6b6b80] mb-6">계정에 로그인하여 아이디어를 관리하세요</p>

            {status === "error" && (
              <div className="mb-4 p-3 rounded-lg bg-[#fef2f2] border border-[#fecaca] text-sm text-[#b91c1c]">
                이메일 또는 비밀번호가 올바르지 않습니다.
              </div>
            )}
            {status === "expired" && (
              <div className="mb-4 p-3 rounded-lg bg-[#fffbeb] border border-[#fde68a] text-sm text-[#b45309]">
                세션이 만료되었습니다. 다시 로그인해 주세요.
              </div>
            )}

            <form onSubmit={handleLogin} className="space-y-4">
              <Input
                label="이메일"
                type="email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                placeholder="이메일 주소"
                required
              />
              <div className="flex flex-col gap-1.5">
                <label className="text-sm font-medium text-[#111118]">비밀번호</label>
                <div className="relative">
                  <input
                    type={showPw ? "text" : "password"}
                    value={password}
                    onChange={(e) => setPassword(e.target.value)}
                    placeholder="비밀번호"
                    className="w-full h-9 rounded-lg border border-[rgba(0,0,0,0.1)] bg-white px-3 pr-10 text-sm text-[#111118] placeholder:text-[#9ca3af] focus:outline-none focus:ring-2 focus:ring-[#4f46e5]/20 focus:border-[#4f46e5] transition-colors"
                  />
                  <button
                    type="button"
                    onClick={() => setShowPw(!showPw)}
                    className="absolute right-3 top-1/2 -translate-y-1/2 text-[#9ca3af] hover:text-[#6b6b80]"
                  >
                    {showPw ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
                  </button>
                </div>
              </div>

              <div className="flex items-center justify-between">
                <label className="flex items-center gap-2 cursor-pointer">
                  <input
                    type="checkbox"
                    checked={remember}
                    onChange={(e) => setRemember(e.target.checked)}
                    className="w-4 h-4 rounded accent-[#4f46e5]"
                  />
                  <span className="text-sm text-[#6b6b80]">로그인 유지</span>
                </label>
                <button type="button" className="text-sm text-[#4f46e5] hover:underline">
                  비밀번호 찾기
                </button>
              </div>

              <Button
                type="submit"
                variant="primary"
                size="lg"
                loading={status === "loading"}
                className="w-full"
                icon={<ArrowRight className="w-4 h-4" />}
              >
                로그인
              </Button>
            </form>

            <div className="mt-6 text-center">
              <span className="text-sm text-[#6b6b80]">계정이 없으신가요? </span>
              <button className="text-sm text-[#4f46e5] font-medium hover:underline">
                회원가입
              </button>
            </div>
          </div>

          <p className="text-center text-xs text-[#9ca3af] mt-6">
            테스트: 아무 비밀번호로 로그인하세요 (wrong 입력 시 오류 표시)
          </p>
        </div>
      </div>
    </div>
  );
}
