import { useState, useEffect } from "react";
import { useNavigate, useParams } from "react-router";
import { clsx } from "clsx";
import {
  Sparkles,
  PenLine,
  Paperclip,
  BookOpen,
  Lightbulb,
  Clock,
  AlertCircle,
  CheckCircle2,
  ArrowRight,
  ChevronRight,
  Globe,
} from "lucide-react";
import { MOCK_IDEAS } from "../../mocks/ideas";
import { MOCK_USERS, getUserById } from "../../mocks/users";
import { Button } from "../../components/common/Button";
import { StageBadge, PriorityBadge } from "../../components/common/Badge";
import { Avatar, AvatarGroup } from "../../components/common/Avatar";
import { Checkbox } from "../../components/common/Input";
import { HomePageSkeleton } from "../../components/common/Skeleton";
import type { IdeaStage } from "../../types";

const STAGE_LABELS: Record<IdeaStage, string> = {
  draft: "초안",
  reviewing: "검토 중",
  validated: "검증 후보",
  executing: "실행 중",
  paused: "보류",
  archived: "보관",
};

const statCards = [
  { stage: "all" as const, label: "전체 아이디어", color: "#4f46e5", bg: "#ede9fe" },
  { stage: "reviewing" as IdeaStage, label: "검토 중", color: "#d97706", bg: "#fffbeb" },
  { stage: "validated" as IdeaStage, label: "검증 후보", color: "#7c3aed", bg: "#f5f3ff" },
  { stage: "executing" as IdeaStage, label: "실행 중", color: "#16a34a", bg: "#f0fdf4" },
  { stage: "paused" as IdeaStage, label: "보류", color: "#6b6b80", bg: "#f0f0f5" },
];

const REVIEW_ITEMS = [
  { id: "idea-008", reason: "검토일 5일 후", type: "scheduled" },
  { id: "idea-004", reason: "30일 동안 미검토", type: "overdue" },
  { id: "idea-001", reason: "유사 아이디어 발견", type: "similar" },
  { id: "idea-005", reason: "AI 초안 미완료", type: "draft" },
];

export function HomePage() {
  const navigate = useNavigate();
  const { workspaceId = "personal" } = useParams();
  const [loading, setLoading] = useState(true);
  const [inputText, setInputText] = useState("");
  const [useWebSearch, setUseWebSearch] = useState(false);
  const [checkSimilar, setCheckSimilar] = useState(true);

  useEffect(() => {
    const t = setTimeout(() => setLoading(false), 800);
    return () => clearTimeout(t);
  }, []);

  const recentIdeas = [...MOCK_IDEAS]
    .sort((a, b) => b.updatedAt.localeCompare(a.updatedAt))
    .slice(0, 5);

  function handleAiSubmit() {
    if (!inputText.trim()) return;
    navigate(`/w/${workspaceId}/ideas/new/ai`, { state: { text: inputText } });
  }

  const ideaCount = MOCK_IDEAS.length;
  const stageCount = (stage: IdeaStage | "all") =>
    stage === "all" ? MOCK_IDEAS.length : MOCK_IDEAS.filter((i) => i.stage === stage).length;

  if (loading) return <HomePageSkeleton />;

  return (
    <div className="px-4 sm:px-8 py-8 max-w-[1200px] mx-auto space-y-8">
      {/* Page header */}
      <div>
        <h1 className="text-2xl font-bold text-[#111118]">안녕하세요, 전창현님 👋</h1>
        <p className="text-sm text-[#6b6b80] mt-1">
          내 작업공간 · 오늘도 떠오른 생각을 기록하고 발전시켜 보세요.
        </p>
      </div>

      {/* Quick input */}
      <div className="bg-white rounded-2xl border border-[rgba(0,0,0,0.07)] p-6 shadow-sm">
        <div className="flex items-center gap-2 mb-1">
          <Sparkles className="w-4.5 h-4.5 text-[#7c3aed]" />
          <h2 className="text-base font-semibold text-[#111118]">새로운 아이디어가 떠올랐나요?</h2>
        </div>
        <p className="text-sm text-[#6b6b80] mb-4">
          완성된 문장이 아니어도 괜찮습니다. 생각나는 대로 자유롭게 적어보세요.
        </p>
        <textarea
          value={inputText}
          onChange={(e) => setInputText(e.target.value)}
          placeholder="어떤 문제를 발견했는지, 누구를 위한 것인지, 어떻게 해결하면 좋을지 자유롭게 적어보세요..."
          className="w-full h-28 rounded-xl border border-[rgba(0,0,0,0.1)] bg-[#f8f8fb] px-4 py-3 text-sm text-[#111118] placeholder:text-[#9ca3af] resize-none focus:outline-none focus:ring-2 focus:ring-[#4f46e5]/15 focus:border-[#4f46e5] focus:bg-white transition-all"
          maxLength={2000}
        />
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 mt-3">
          <div className="flex flex-wrap items-center gap-3 sm:gap-4">
            <Checkbox
              label="웹 검색 포함"
              checked={useWebSearch}
              onChange={(e) => setUseWebSearch(e.target.checked)}
            />
            <Checkbox
              label="유사 아이디어 확인"
              checked={checkSimilar}
              onChange={(e) => setCheckSimilar(e.target.checked)}
            />
            <button className="flex items-center gap-1 text-sm text-[#6b6b80] hover:text-[#4f46e5]">
              <Paperclip className="w-3.5 h-3.5" />
            </button>
            <button className="hidden sm:flex items-center gap-1 text-xs text-[#6b6b80] hover:text-[#4f46e5]">
              <BookOpen className="w-3.5 h-3.5" />
              <span>예시 보기</span>
            </button>
          </div>
          <div className="flex items-center gap-2 justify-end">
            <span className="text-xs text-[#9ca3af] font-mono">{inputText.length}/2000</span>
            <Button
              variant="secondary"
              size="sm"
              icon={<PenLine className="w-3.5 h-3.5" />}
              onClick={() => navigate(`/w/${workspaceId}/ideas/new`)}
            >
              직접 등록
            </Button>
            <Button
              variant="ai"
              size="sm"
              icon={<Sparkles className="w-3.5 h-3.5" />}
              onClick={handleAiSubmit}
              disabled={!inputText.trim()}
            >
              AI로 정리하기
            </Button>
          </div>
        </div>
      </div>

      {/* Stats row */}
      <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-5 gap-4">
        {statCards.map((card) => {
          const count = stageCount(card.stage);
          return (
            <button
              key={card.label}
              onClick={() => navigate(`/w/${workspaceId}/ideas`)}
              className="bg-white rounded-xl border border-[rgba(0,0,0,0.07)] p-4 text-left hover:border-[rgba(0,0,0,0.12)] hover:shadow-sm transition-all group"
            >
              <p className="text-2xl font-bold text-[#111118] mb-1">{count}</p>
              <p className="text-xs text-[#6b6b80]">{card.label}</p>
              <div
                className="w-6 h-0.5 rounded-full mt-2 transition-all group-hover:w-8"
                style={{ backgroundColor: card.color }}
              />
            </button>
          );
        })}
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Recent ideas */}
        <div className="lg:col-span-2 bg-white rounded-2xl border border-[rgba(0,0,0,0.07)] shadow-sm overflow-hidden">
          <div className="flex items-center justify-between px-5 py-4 border-b border-[rgba(0,0,0,0.06)]">
            <h3 className="text-sm font-semibold text-[#111118]">최근 아이디어</h3>
            <button
              onClick={() => navigate(`/w/${workspaceId}/ideas`)}
              className="text-xs text-[#4f46e5] hover:underline flex items-center gap-1"
            >
              전체 보기 <ChevronRight className="w-3.5 h-3.5" />
            </button>
          </div>
          <div className="divide-y divide-[rgba(0,0,0,0.05)]">
            {recentIdeas.map((idea) => {
              const author = getUserById(idea.authorId);
              return (
                <button
                  key={idea.id}
                  onClick={() => navigate(`/w/${workspaceId}/ideas/${idea.id}`)}
                  className="w-full flex items-center gap-3 px-5 py-3.5 hover:bg-[#f8f8fb] text-left transition-colors group"
                >
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2 mb-0.5">
                      <span className="text-xs font-mono text-[#9ca3af]">{idea.code}</span>
                      <StageBadge stage={idea.stage} />
                    </div>
                    <p className="text-sm font-medium text-[#111118] truncate">{idea.title}</p>
                    <p className="text-xs text-[#6b6b80] truncate">{idea.oneLiner}</p>
                  </div>
                  <div className="flex items-center gap-3 shrink-0">
                    {author && <Avatar user={author} size="xs" />}
                    <span className="text-xs text-[#9ca3af] hidden sm:block">
                      {new Date(idea.updatedAt).toLocaleDateString("ko")}
                    </span>
                    <ChevronRight className="w-4 h-4 text-[#d1d5db] group-hover:text-[#6b6b80] transition-colors" />
                  </div>
                </button>
              );
            })}
          </div>
        </div>

        {/* Right column */}
        <div className="space-y-4">
          {/* Todo */}
          <div className="bg-white rounded-2xl border border-[rgba(0,0,0,0.07)] shadow-sm">
            <div className="px-5 py-4 border-b border-[rgba(0,0,0,0.06)]">
              <h3 className="text-sm font-semibold text-[#111118]">내 할 일</h3>
            </div>
            <div className="divide-y divide-[rgba(0,0,0,0.05)]">
              {[
                { icon: Clock, label: "검토 예정", count: 2, color: "#d97706" },
                { icon: AlertCircle, label: "검토일 경과", count: 1, color: "#dc2626" },
                { icon: Lightbulb, label: "담당 아이디어", count: 4, color: "#4f46e5" },
                { icon: CheckCircle2, label: "미완료 AI 초안", count: 1, color: "#7c3aed" },
              ].map((item) => (
                <button
                  key={item.label}
                  className="w-full flex items-center gap-3 px-5 py-3 hover:bg-[#f8f8fb] transition-colors"
                >
                  <item.icon className="w-4 h-4 shrink-0" style={{ color: item.color }} />
                  <span className="flex-1 text-sm text-[#111118] text-left">{item.label}</span>
                  <span
                    className="text-xs font-semibold px-1.5 py-0.5 rounded-full"
                    style={{ color: item.color, backgroundColor: item.color + "18" }}
                  >
                    {item.count}
                  </span>
                </button>
              ))}
            </div>
          </div>

          {/* Review recommendations */}
          <div className="bg-white rounded-2xl border border-[rgba(0,0,0,0.07)] shadow-sm">
            <div className="px-5 py-4 border-b border-[rgba(0,0,0,0.06)]">
              <h3 className="text-sm font-semibold text-[#111118]">추천 검토</h3>
            </div>
            <div className="divide-y divide-[rgba(0,0,0,0.05)]">
              {REVIEW_ITEMS.map((item) => {
                const idea = MOCK_IDEAS.find((i) => i.id === item.id);
                if (!idea) return null;
                return (
                  <button
                    key={item.id}
                    onClick={() => navigate(`/w/${workspaceId}/ideas/${item.id}`)}
                    className="w-full flex items-start gap-3 px-5 py-3 hover:bg-[#f8f8fb] text-left transition-colors"
                  >
                    <div className="flex-1 min-w-0">
                      <p className="text-sm font-medium text-[#111118] truncate">{idea.title}</p>
                      <p className="text-xs text-[#6b6b80]">{item.reason}</p>
                    </div>
                    <ChevronRight className="w-4 h-4 text-[#d1d5db] mt-0.5 shrink-0" />
                  </button>
                );
              })}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
