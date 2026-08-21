import { useState } from "react";
import { useNavigate, useParams, NavLink, useSearchParams } from "react-router";
import { clsx } from "clsx";
import {
  Star,
  Share2,
  Pencil,
  Sparkles,
  MoreHorizontal,
  ChevronRight,
  MessageSquare,
  History,
  BookOpen,
  FileText,
  X,
  Send,
  RefreshCw,
  Clock,
  User,
} from "lucide-react";
import { MOCK_IDEAS } from "../../mocks/ideas";
import { getUserById } from "../../mocks/users";
import { MOCK_EVIDENCE } from "../../mocks/evidence";
import { Button } from "../../components/common/Button";
import { toast } from "../../components/common/Toast";
import {
  StageBadge,
  PriorityBadge,
  FeasibilityBadge,
  VisibilityBadge,
} from "../../components/common/Badge";
import { Avatar, AvatarGroup } from "../../components/common/Avatar";
import { EmptyState } from "../../components/common/EmptyState";

type DetailTab = "overview" | "research" | "discussion" | "history";

const AI_EVOLVE_OPTIONS = [
  "더 구체적으로 확장",
  "기술 구현 관점",
  "사업화 관점",
  "사용자 관점",
  "반대 관점",
  "위험 분석",
  "최소 검증안",
  "다음 실행 항목",
];

const HISTORY_ITEMS = [
  { type: "ai_structured", desc: "AI 구조화 완료 — Qwen3-14B 사용", date: "2026-07-22 14:30", actor: "u-001" },
  { type: "web_searched", desc: "웹 검색 실행 — 5개 출처 수집", date: "2026-07-22 14:28", actor: "u-001" },
  { type: "created", desc: "아이디어 등록", date: "2026-07-10 09:00", actor: "u-001" },
];

export function IdeaDetailPage() {
  const navigate = useNavigate();
  const { workspaceId = "personal", ideaId = "idea-001" } = useParams();
  const [searchParams, setSearchParams] = useSearchParams();
  const tabParam = (searchParams.get("tab") as DetailTab) || "overview";
  const tab = tabParam;

  function setTab(t: DetailTab) {
    setSearchParams({ tab: t }, { replace: true });
  }
  const [aiDrawer, setAiDrawer] = useState(false);
  const [comment, setComment] = useState("");
  const [isFav, setIsFav] = useState(false);

  function handleShare() {
    navigator.clipboard?.writeText(window.location.href).catch(() => {});
    toast.success("링크가 복사되었습니다");
  }

  function handleCommentSubmit() {
    if (!comment.trim()) return;
    setComment("");
    toast.success("댓글이 게시되었습니다");
  }

  const idea = MOCK_IDEAS.find((i) => i.id === ideaId) ?? MOCK_IDEAS[0];
  const author = getUserById(idea.authorId);
  const assignee = idea.assigneeId ? getUserById(idea.assigneeId) : null;
  const participants = idea.participantIds.map((id) => getUserById(id)).filter(Boolean) as any[];

  const TABS: { id: DetailTab; label: string; icon: any }[] = [
    { id: "overview", label: "개요", icon: FileText },
    { id: "research", label: "조사 및 근거", icon: BookOpen },
    { id: "discussion", label: "논의", icon: MessageSquare },
    { id: "history", label: "이력", icon: History },
  ];

  const sections = [
    { label: "배경", value: idea.background },
    { label: "해결하려는 문제", value: idea.problem },
    { label: "핵심 개념", value: idea.concept },
    { label: "주요 기능", value: idea.features },
    { label: "기대 효과", value: idea.expectedEffect },
    { label: "예상 사용자", value: idea.targetUsers },
    { label: "사용 시나리오", value: idea.scenario },
    { label: "주요 난제", value: idea.challenges },
    { label: "최소 검증 방법", value: idea.validationMethod },
  ];

  return (
    <div className="flex h-full">
      <div className={clsx("flex-1 flex flex-col overflow-hidden transition-all", aiDrawer && "xl:mr-80")}>
        {/* Header */}
        <div className="px-4 sm:px-8 pt-6 pb-4 bg-white border-b border-[rgba(0,0,0,0.06)]">
          {/* Breadcrumb */}
          <div className="flex items-center gap-1.5 text-xs text-[#6b6b80] mb-4">
            <button onClick={() => navigate(`/w/${workspaceId}/ideas`)} className="hover:text-[#4f46e5]">
              아이디어
            </button>
            <ChevronRight className="w-3 h-3" />
            <span className="text-[#9ca3af]">{idea.code}</span>
          </div>

          <div className="flex items-start justify-between gap-4">
            <div className="flex-1 min-w-0">
              <div className="flex items-center gap-2 mb-2">
                <span className="text-xs font-mono text-[#9ca3af]">{idea.code}</span>
                <StageBadge stage={idea.stage} />
              </div>
              <h1 className="text-2xl font-bold text-[#111118] mb-1">{idea.title}</h1>
              <p className="text-base text-[#6b6b80]">{idea.oneLiner}</p>
              <div className="flex items-center gap-4 mt-3 text-xs text-[#9ca3af]">
                {author && (
                  <div className="flex items-center gap-1.5">
                    <Avatar user={author} size="xs" />
                    <span>{author.name}</span>
                  </div>
                )}
                <span>최종 수정 {new Date(idea.updatedAt).toLocaleDateString("ko")}</span>
              </div>
            </div>
            <div className="flex items-center gap-1 sm:gap-1.5 shrink-0">
              <Button variant="icon" onClick={() => setIsFav(!isFav)} title="즐겨찾기">
                <Star className={clsx("w-4 h-4", isFav && "fill-[#d97706] text-[#d97706]")} />
              </Button>
              <Button variant="icon" title="공유" onClick={handleShare} className="hidden sm:flex"><Share2 className="w-4 h-4" /></Button>
              <Button
                variant="secondary"
                size="sm"
                icon={<Pencil className="w-3.5 h-3.5" />}
                onClick={() => navigate(`/w/${workspaceId}/ideas/${ideaId}/edit`)}
              >
                <span className="hidden sm:inline">편집</span>
              </Button>
              <Button
                variant="ai"
                size="sm"
                icon={<Sparkles className="w-3.5 h-3.5" />}
                onClick={() => setAiDrawer(true)}
              >
                <span className="hidden sm:inline">AI로 발전시키기</span>
              </Button>
              <Button variant="icon"><MoreHorizontal className="w-4 h-4" /></Button>
            </div>
          </div>

          {/* Meta */}
          <div className="flex flex-wrap gap-4 mt-4 pt-4 border-t border-[rgba(0,0,0,0.05)]">
            <MetaItem label="분야" value={idea.field} />
            <MetaItem label="우선순위" value={<PriorityBadge priority={idea.priority} />} />
            <MetaItem label="구현 가능성" value={<FeasibilityBadge feasibility={idea.feasibility} />} />
            <MetaItem label="공개 범위" value={<VisibilityBadge visibility={idea.visibility} />} />
            {assignee && (
              <MetaItem
                label="담당자"
                value={
                  <div className="flex items-center gap-1.5">
                    <Avatar user={assignee} size="xs" />
                    <span className="text-sm text-[#111118]">{assignee.name}</span>
                  </div>
                }
              />
            )}
            <MetaItem
              label="참여자"
              value={<AvatarGroup users={participants} max={4} size="xs" />}
            />
            {idea.nextReviewDate && (
              <MetaItem label="다음 검토일" value={idea.nextReviewDate} />
            )}
          </div>

          {/* Tabs */}
          <div className="flex gap-0.5 mt-4 -mb-px">
            {TABS.map((t) => (
              <button
                key={t.id}
                onClick={() => setTab(t.id)}
                className={clsx(
                  "flex items-center gap-1.5 px-3 py-2 text-sm font-medium border-b-2 transition-colors",
                  tab === t.id
                    ? "border-[#4f46e5] text-[#4f46e5]"
                    : "border-transparent text-[#6b6b80] hover:text-[#111118]"
                )}
              >
                <t.icon className="w-3.5 h-3.5" />
                {t.label}
              </button>
            ))}
          </div>
        </div>

        {/* Tab content */}
        <div className="flex-1 overflow-y-auto px-4 sm:px-8 py-6">
          {tab === "overview" && (
            <div className="max-w-2xl space-y-6">
              {sections.map((s) =>
                s.value ? (
                  <div key={s.label}>
                    <h4 className="text-xs font-semibold text-[#6b6b80] uppercase tracking-wider mb-2">
                      {s.label}
                    </h4>
                    <p className="text-sm text-[#111118] leading-relaxed">{s.value}</p>
                  </div>
                ) : null
              )}
            </div>
          )}

          {tab === "research" && (
            <div className="max-w-2xl space-y-4">
              <div className="flex items-center justify-between mb-2">
                <h3 className="text-sm font-semibold text-[#111118]">출처 및 근거</h3>
                <Button variant="ghost" size="sm" icon={<RefreshCw className="w-3.5 h-3.5" />}>다시 조사</Button>
              </div>
              {MOCK_EVIDENCE.map((ev) => (
                <div key={ev.id} className="bg-white rounded-xl border border-[rgba(0,0,0,0.07)] p-4">
                  <div className="flex items-start justify-between gap-2 mb-2">
                    <p className="text-sm font-semibold text-[#111118]">{ev.title}</p>
                    <span className={clsx(
                      "text-xs px-2 py-0.5 rounded-full shrink-0",
                      ev.status === "applied" && "bg-[#f0fdf4] text-[#16a34a]",
                      ev.status === "partial" && "bg-[#fffbeb] text-[#d97706]",
                      ev.status === "reference" && "bg-[#f0f0f5] text-[#6b6b80]",
                      ev.status === "excluded" && "bg-[#fef2f2] text-[#dc2626]",
                      ev.status === "needs_check" && "bg-[#fef3c7] text-[#b45309]",
                    )}>
                      {ev.status === "applied" && "반영됨"}
                      {ev.status === "partial" && "일부 반영"}
                      {ev.status === "reference" && "참고만 함"}
                      {ev.status === "excluded" && "제외됨"}
                      {ev.status === "needs_check" && "신뢰도 확인 필요"}
                    </span>
                  </div>
                  <p className="text-xs text-[#6b6b80] mb-2">{ev.publisher} · {ev.publishedAt}</p>
                  <p className="text-sm text-[#111118] leading-relaxed mb-3">{ev.summary}</p>
                  <div className="flex items-center justify-between">
                    <div className="flex gap-1 flex-wrap">
                      {ev.relatedFields.map((f) => (
                        <span key={f} className="text-xs px-1.5 py-0.5 rounded-md bg-[#ede9fe] text-[#7c3aed]">{f}</span>
                      ))}
                    </div>
                    <a href={ev.url} className="text-xs text-[#4f46e5] hover:underline">원문 보기 →</a>
                  </div>
                </div>
              ))}
            </div>
          )}

          {tab === "discussion" && (
            <div className="max-w-xl space-y-4">
              {[
                { authorId: "u-002", body: "신뢰 모델 부분을 더 구체화하면 어떨까요? 특히 악의적인 에이전트 처리 방안이 궁금합니다.", date: "2026-07-22" },
                { authorId: "u-001", body: "좋은 지적입니다. 제로 트러스트 접근 방식을 우선 검토하고 있습니다.", date: "2026-07-23" },
              ].map((c, i) => {
                const u = getUserById(c.authorId);
                return u ? (
                  <div key={i} className="flex gap-3">
                    <Avatar user={u} size="sm" />
                    <div className="flex-1">
                      <div className="flex items-center gap-2 mb-1">
                        <span className="text-sm font-semibold text-[#111118]">{u.name}</span>
                        <span className="text-xs text-[#9ca3af]">{c.date}</span>
                      </div>
                      <p className="text-sm text-[#111118] leading-relaxed">{c.body}</p>
                    </div>
                  </div>
                ) : null;
              })}
              <div className="flex gap-3 pt-2 border-t border-[rgba(0,0,0,0.06)]">
                <Avatar user={{ id: "u-001", name: "전창현", avatarInitials: "전", avatarColor: "#4f46e5", email: "", role: "user" }} size="sm" />
                <div className="flex-1">
                  <textarea
                    value={comment}
                    onChange={(e) => setComment(e.target.value)}
                    placeholder="댓글을 작성하세요..."
                    className="w-full h-20 rounded-lg border border-[rgba(0,0,0,0.1)] bg-white px-3 py-2 text-sm resize-none focus:outline-none focus:ring-2 focus:ring-[#4f46e5]/20 focus:border-[#4f46e5]"
                  />
                  <div className="flex justify-end mt-2">
                    <Button variant="primary" size="sm" icon={<Send className="w-3.5 h-3.5" />} disabled={!comment.trim()} onClick={handleCommentSubmit}>
                      게시
                    </Button>
                  </div>
                </div>
              </div>
            </div>
          )}

          {tab === "history" && (
            <div className="max-w-xl space-y-0">
              {HISTORY_ITEMS.map((h, i) => {
                const actor = getUserById(h.actor);
                return (
                  <div key={i} className="flex gap-3 pb-6 relative">
                    {i < HISTORY_ITEMS.length - 1 && (
                      <div className="absolute left-3.5 top-7 bottom-0 w-px bg-[rgba(0,0,0,0.07)]" />
                    )}
                    <div className="w-7 h-7 rounded-full bg-[#f0f0f5] border border-white flex items-center justify-center shrink-0 z-10">
                      {h.type === "ai_structured" && <Sparkles className="w-3.5 h-3.5 text-[#7c3aed]" />}
                      {h.type === "web_searched" && <BookOpen className="w-3.5 h-3.5 text-[#2563eb]" />}
                      {h.type === "created" && <FileText className="w-3.5 h-3.5 text-[#16a34a]" />}
                    </div>
                    <div>
                      <p className="text-sm text-[#111118]">{h.desc}</p>
                      <p className="text-xs text-[#9ca3af] mt-0.5">
                        {actor?.name} · {h.date}
                      </p>
                    </div>
                  </div>
                );
              })}
            </div>
          )}
        </div>
      </div>

      {/* AI evolve drawer */}
      {aiDrawer && (
        <div className="fixed right-0 top-16 bottom-0 w-80 bg-white border-l border-[rgba(0,0,0,0.08)] shadow-xl z-30 flex flex-col">
          <div className="flex items-center justify-between px-5 py-4 border-b border-[rgba(0,0,0,0.06)]">
            <div className="flex items-center gap-2">
              <Sparkles className="w-4 h-4 text-[#7c3aed]" />
              <p className="text-sm font-semibold text-[#111118]">AI로 발전시키기</p>
            </div>
            <button
              onClick={() => setAiDrawer(false)}
              className="w-7 h-7 flex items-center justify-center rounded-lg text-[#6b6b80] hover:bg-[#f4f4f8]"
            >
              <X className="w-4 h-4" />
            </button>
          </div>
          <div className="flex-1 overflow-y-auto p-4">
            <p className="text-xs text-[#6b6b80] mb-3">발전 방향을 선택하세요. 결과는 변경 초안으로 표시됩니다.</p>
            <div className="space-y-2">
              {AI_EVOLVE_OPTIONS.map((opt) => (
                <button
                  key={opt}
                  className="w-full text-left px-3 py-2.5 rounded-lg border border-[rgba(0,0,0,0.08)] hover:border-[#7c3aed]/30 hover:bg-[#f5f3ff] text-sm text-[#111118] transition-all"
                >
                  {opt}
                </button>
              ))}
            </div>
            <div className="mt-6 p-4 rounded-xl bg-[#f5f3ff] border border-[#ede9fe]">
              <p className="text-xs font-medium text-[#7c3aed] mb-1">미리보기 (샘플)</p>
              <p className="text-xs text-[#6b6b80] leading-relaxed">
                선택하면 AI가 해당 관점으로 초안을 생성합니다. 저장 전 검토할 수 있습니다.
              </p>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

function MetaItem({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <div>
      <p className="text-xs text-[#9ca3af] mb-0.5">{label}</p>
      {typeof value === "string" ? (
        <p className="text-sm font-medium text-[#111118]">{value}</p>
      ) : (
        value
      )}
    </div>
  );
}
