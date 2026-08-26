import { useState, useEffect } from "react";
import { useNavigate, useParams } from "react-router";
import {
  Sparkles,
  PenLine,
  Paperclip,
  BookOpen,
  Lightbulb,
  Clock,
  AlertCircle,
  CheckCircle2,
  ChevronRight,
} from "lucide-react";
import { listIdeas } from "../../api/ideas";
import { useAuth } from "../../auth/AuthProvider";
import { useWorkspace } from "../../workspace/WorkspaceProvider";
import { Button } from "../../components/common/Button";
import { StageLabelBadge } from "../../components/common/Badge";
import { Avatar } from "../../components/common/Avatar";
import { Checkbox } from "../../components/common/Input";
import { HomePageSkeleton } from "../../components/common/Skeleton";
import { toDisplayUser } from "../../utils/avatar";
import type { IdeaListItem } from "../../types/api";

export function HomePage() {
  const navigate = useNavigate();
  const { workspaceId = "" } = useParams();
  const { user } = useAuth();
  const { currentWorkspace } = useWorkspace();
  const [loading, setLoading] = useState(true);
  const [recentIdeas, setRecentIdeas] = useState<IdeaListItem[]>([]);
  const [totalCount, setTotalCount] = useState(0);
  const [assignedCount, setAssignedCount] = useState<number | null>(null);
  const [inputText, setInputText] = useState("");
  const [useWebSearch, setUseWebSearch] = useState(false);
  const [checkSimilar, setCheckSimilar] = useState(true);

  useEffect(() => {
    if (!workspaceId || !user) return;
    let cancelled = false;
    setLoading(true);
    void Promise.all([
      listIdeas(workspaceId, { limit: 5, offset: 0 }),
      listIdeas(workspaceId, { limit: 1, offset: 0, assignee_id: user.id }),
    ])
      .then(([recent, assigned]) => {
        if (cancelled) return;
        setRecentIdeas(recent.items);
        setTotalCount(recent.total);
        setAssignedCount(assigned.total);
      })
      .catch(() => {
        if (!cancelled) {
          setRecentIdeas([]);
          setTotalCount(0);
          setAssignedCount(null);
        }
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [workspaceId, user]);

  function handleAiSubmit() {
    if (!inputText.trim()) return;
    navigate(`/w/${workspaceId}/ideas/new/ai`, { state: { text: inputText } });
  }

  const statCards = [
    { label: "전체 아이디어", count: totalCount, color: "#4f46e5" },
    { label: "검토 중", count: "—", color: "#d97706" },
    { label: "검증 후보", count: "—", color: "#7c3aed" },
    { label: "실행 중", count: "—", color: "#16a34a" },
    { label: "보류", count: "—", color: "#6b6b80" },
  ];

  if (loading) return <HomePageSkeleton />;

  const greetingName = user?.name ?? "사용자";
  const workspaceName = currentWorkspace?.name ?? "작업공간";

  return (
    <div className="px-4 sm:px-8 py-8 max-w-[1200px] mx-auto space-y-8">
      <div>
        <h1 className="text-2xl font-bold text-[#111118]">안녕하세요, {greetingName}님 👋</h1>
        <p className="text-sm text-[#6b6b80] mt-1">
          {workspaceName} · 오늘도 떠오른 생각을 기록하고 발전시켜 보세요.
        </p>
      </div>

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
            <Checkbox label="웹 검색 포함" checked={useWebSearch} onChange={(e) => setUseWebSearch(e.target.checked)} />
            <Checkbox label="유사 아이디어 확인" checked={checkSimilar} onChange={(e) => setCheckSimilar(e.target.checked)} />
            <button type="button" className="flex items-center gap-1 text-sm text-[#6b6b80] hover:text-[#4f46e5]">
              <Paperclip className="w-3.5 h-3.5" />
            </button>
            <button type="button" className="hidden sm:flex items-center gap-1 text-xs text-[#6b6b80] hover:text-[#4f46e5]">
              <BookOpen className="w-3.5 h-3.5" />
              <span>예시 보기</span>
            </button>
          </div>
          <div className="flex items-center gap-2 justify-end">
            <span className="text-xs text-[#9ca3af] font-mono">{inputText.length}/2000</span>
            <Button variant="secondary" size="sm" icon={<PenLine className="w-3.5 h-3.5" />} onClick={() => navigate(`/w/${workspaceId}/ideas/new`)}>
              직접 등록
            </Button>
            <Button variant="ai" size="sm" icon={<Sparkles className="w-3.5 h-3.5" />} onClick={handleAiSubmit} disabled={!inputText.trim()}>
              AI로 정리하기
            </Button>
          </div>
        </div>
      </div>

      <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-5 gap-4">
        {statCards.map((card) => (
          <button
            key={card.label}
            type="button"
            onClick={() => navigate(`/w/${workspaceId}/ideas`)}
            className="bg-white rounded-xl border border-[rgba(0,0,0,0.07)] p-4 text-left hover:border-[rgba(0,0,0,0.12)] hover:shadow-sm transition-all group"
          >
            <p className="text-2xl font-bold text-[#111118] mb-1">{card.count}</p>
            <p className="text-xs text-[#6b6b80]">{card.label}</p>
            <div className="w-6 h-0.5 rounded-full mt-2 transition-all group-hover:w-8" style={{ backgroundColor: card.color }} />
          </button>
        ))}
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        <div className="lg:col-span-2 bg-white rounded-2xl border border-[rgba(0,0,0,0.07)] shadow-sm overflow-hidden">
          <div className="flex items-center justify-between px-5 py-4 border-b border-[rgba(0,0,0,0.06)]">
            <h3 className="text-sm font-semibold text-[#111118]">최근 아이디어</h3>
            <button type="button" onClick={() => navigate(`/w/${workspaceId}/ideas`)} className="text-xs text-[#4f46e5] hover:underline flex items-center gap-1">
              전체 보기 <ChevronRight className="w-3.5 h-3.5" />
            </button>
          </div>
          {recentIdeas.length === 0 ? (
            <div className="px-5 py-8 text-center text-sm text-[#6b6b80]">등록된 아이디어가 없습니다.</div>
          ) : (
            <div className="divide-y divide-[rgba(0,0,0,0.05)]">
              {recentIdeas.map((idea) => {
                const author = toDisplayUser(idea.author);
                return (
                  <button
                    key={idea.id}
                    type="button"
                    onClick={() => navigate(`/w/${workspaceId}/ideas/${idea.id}`)}
                    className="w-full flex items-center gap-3 px-5 py-3.5 hover:bg-[#f8f8fb] text-left transition-colors group"
                  >
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center gap-2 mb-0.5">
                        <span className="text-xs font-mono text-[#9ca3af]">{idea.idea_code}</span>
                        <StageLabelBadge label={idea.stage.label} />
                      </div>
                      <p className="text-sm font-medium text-[#111118] truncate">{idea.title}</p>
                      <p className="text-xs text-[#6b6b80] truncate">{idea.one_line_definition ?? ""}</p>
                    </div>
                    <div className="flex items-center gap-3 shrink-0">
                      <Avatar user={author} size="xs" />
                      <span className="text-xs text-[#9ca3af] hidden sm:block">
                        {new Date(idea.updated_at).toLocaleDateString("ko")}
                      </span>
                      <ChevronRight className="w-4 h-4 text-[#d1d5db] group-hover:text-[#6b6b80] transition-colors" />
                    </div>
                  </button>
                );
              })}
            </div>
          )}
        </div>

        <div className="space-y-4">
          <div className="bg-white rounded-2xl border border-[rgba(0,0,0,0.07)] shadow-sm">
            <div className="px-5 py-4 border-b border-[rgba(0,0,0,0.06)]">
              <h3 className="text-sm font-semibold text-[#111118]">내 할 일</h3>
            </div>
            <div className="divide-y divide-[rgba(0,0,0,0.05)]">
              {[
                { icon: Clock, label: "검토 예정", count: "—", color: "#d97706" },
                { icon: AlertCircle, label: "검토일 경과", count: "—", color: "#dc2626" },
                { icon: Lightbulb, label: "담당 아이디어", count: assignedCount ?? "—", color: "#4f46e5" },
                { icon: CheckCircle2, label: "미완료 AI 초안", count: "—", color: "#7c3aed" },
              ].map((item) => (
                <button key={item.label} type="button" className="w-full flex items-center gap-3 px-5 py-3 hover:bg-[#f8f8fb] transition-colors">
                  <item.icon className="w-4 h-4 shrink-0" style={{ color: item.color }} />
                  <span className="flex-1 text-sm text-[#111118] text-left">{item.label}</span>
                  <span className="text-xs font-semibold px-1.5 py-0.5 rounded-full" style={{ color: item.color, backgroundColor: item.color + "18" }}>
                    {item.count}
                  </span>
                </button>
              ))}
            </div>
          </div>

          <div className="bg-white rounded-2xl border border-[rgba(0,0,0,0.07)] shadow-sm">
            <div className="px-5 py-4 border-b border-[rgba(0,0,0,0.06)]">
              <h3 className="text-sm font-semibold text-[#111118]">추천 검토</h3>
            </div>
            <div className="px-5 py-8 text-center text-sm text-[#6b6b80]">
              Review API 연동 전까지 추천 검토가 제공되지 않습니다.
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
