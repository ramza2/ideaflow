import { useEffect, useState } from "react";
import { useNavigate, useParams, useSearchParams } from "react-router";
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
  Trash2,
} from "lucide-react";
import { deleteIdea, getIdea } from "../../api/ideas";
import { ApiError, apiErrorMessage } from "../../api/client";
import { MOCK_EVIDENCE } from "../../mocks/evidence";
import { Button } from "../../components/common/Button";
import { toast } from "../../components/common/Toast";
import {
  ApiFeasibilityBadge,
  ApiPriorityBadge,
  ApiVisibilityBadge,
  StageLabelBadge,
} from "../../components/common/Badge";
import { Avatar } from "../../components/common/Avatar";
import { EmptyState } from "../../components/common/EmptyState";
import { ConfirmDialog } from "../../components/common/ConfirmDialog";
import { toDisplayUser } from "../../utils/avatar";
import type { IdeaDetail } from "../../types/api";

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

export function IdeaDetailPage() {
  const navigate = useNavigate();
  const { workspaceId = "", ideaId = "" } = useParams();
  const [searchParams, setSearchParams] = useSearchParams();
  const tabParam = (searchParams.get("tab") as DetailTab) || "overview";
  const tab = tabParam;

  const [idea, setIdea] = useState<IdeaDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [aiDrawer, setAiDrawer] = useState(false);
  const [comment, setComment] = useState("");
  const [isFav, setIsFav] = useState(false);
  const [deleteOpen, setDeleteOpen] = useState(false);
  const [deleting, setDeleting] = useState(false);

  function setTab(t: DetailTab) {
    setSearchParams({ tab: t }, { replace: true });
  }

  useEffect(() => {
    if (!workspaceId || !ideaId) return;
    let cancelled = false;
    setLoading(true);
    setError(null);
    void getIdea(workspaceId, ideaId)
      .then((data) => {
        if (!cancelled) setIdea(data);
      })
      .catch((err) => {
        if (cancelled) return;
        if (err instanceof ApiError && (err.status === 404 || err.code === "IDEA_NOT_FOUND")) {
          setError("존재하지 않거나 접근할 수 없는 아이디어입니다.");
        } else {
          setError(apiErrorMessage(err));
        }
        setIdea(null);
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [workspaceId, ideaId]);

  function handleShare() {
    navigator.clipboard?.writeText(window.location.href).catch(() => {});
    toast.success("링크가 복사되었습니다");
  }

  function handleCommentSubmit() {
    if (!comment.trim()) return;
    setComment("");
    toast.success("댓글이 게시되었습니다");
  }

  async function handleDelete() {
    if (!workspaceId || !ideaId) return;
    setDeleting(true);
    try {
      await deleteIdea(workspaceId, ideaId);
      toast.success("아이디어가 삭제되었습니다.");
      navigate(`/w/${workspaceId}/ideas`, { replace: true });
    } catch (err) {
      toast.error(apiErrorMessage(err, "삭제에 실패했습니다."));
    } finally {
      setDeleting(false);
      setDeleteOpen(false);
    }
  }

  if (loading) {
    return <div className="p-8 text-sm text-[#6b6b80]">불러오는 중...</div>;
  }

  if (error || !idea) {
    return (
      <div className="p-8">
        <EmptyState
          title="아이디어를 불러올 수 없습니다"
          description={error ?? "존재하지 않거나 접근할 수 없는 아이디어입니다."}
          action={
            <Button variant="secondary" size="sm" onClick={() => navigate(`/w/${workspaceId}/ideas`)}>
              목록으로
            </Button>
          }
        />
      </div>
    );
  }

  const canEdit = idea.current_user_access === "OWNER" || idea.current_user_access === "EDIT";
  const canDelete = idea.current_user_access === "OWNER";
  const author = toDisplayUser(idea.author);
  const assignee = idea.assignee ? toDisplayUser(idea.assignee) : null;

  const TABS: { id: DetailTab; label: string; icon: typeof FileText }[] = [
    { id: "overview", label: "개요", icon: FileText },
    { id: "research", label: "조사 및 근거", icon: BookOpen },
    { id: "discussion", label: "논의", icon: MessageSquare },
    { id: "history", label: "이력", icon: History },
  ];

  const sections = [
    { label: "배경", value: idea.background },
    { label: "해결하려는 문제", value: idea.problem },
    { label: "핵심 개념", value: idea.core_concept },
    { label: "주요 기능", value: idea.major_features },
    { label: "기대 효과", value: idea.expected_effect },
    { label: "예상 사용자", value: idea.target_users },
    { label: "사용 시나리오", value: idea.scenarios },
    { label: "주요 난제", value: idea.challenges },
    { label: "최소 검증 방법", value: idea.minimum_validation },
    { label: "관련 프로젝트", value: idea.related_project },
  ];

  if (idea.original_text && idea.current_user_access === "OWNER") {
    sections.unshift({ label: "원문", value: idea.original_text });
  }

  return (
    <div className="flex h-full">
      <div className={clsx("flex-1 flex flex-col overflow-hidden transition-all", aiDrawer && "xl:mr-80")}>
        <div className="px-4 sm:px-8 pt-6 pb-4 bg-white border-b border-[rgba(0,0,0,0.06)]">
          <div className="flex items-center gap-1.5 text-xs text-[#6b6b80] mb-4">
            <button type="button" onClick={() => navigate(`/w/${workspaceId}/ideas`)} className="hover:text-[#4f46e5]">
              아이디어
            </button>
            <ChevronRight className="w-3 h-3" />
            <span className="text-[#9ca3af]">{idea.idea_code}</span>
          </div>

          <div className="flex items-start justify-between gap-4">
            <div className="flex-1 min-w-0">
              <div className="flex items-center gap-2 mb-2">
                <span className="text-xs font-mono text-[#9ca3af]">{idea.idea_code}</span>
                <StageLabelBadge label={idea.stage.label} />
              </div>
              <h1 className="text-2xl font-bold text-[#111118] mb-1">{idea.title}</h1>
              <p className="text-base text-[#6b6b80]">{idea.one_line_definition ?? ""}</p>
              <div className="flex items-center gap-4 mt-3 text-xs text-[#9ca3af]">
                <div className="flex items-center gap-1.5">
                  <Avatar user={author} size="xs" />
                  <span>{author.name}</span>
                </div>
                <span>최종 수정 {new Date(idea.updated_at).toLocaleDateString("ko")}</span>
              </div>
            </div>
            <div className="flex items-center gap-1 sm:gap-1.5 shrink-0">
              <Button variant="icon" onClick={() => setIsFav(!isFav)} title="즐겨찾기">
                <Star className={clsx("w-4 h-4", isFav && "fill-[#d97706] text-[#d97706]")} />
              </Button>
              <Button variant="icon" title="공유" onClick={handleShare} className="hidden sm:flex"><Share2 className="w-4 h-4" /></Button>
              {canEdit && (
                <Button
                  variant="secondary"
                  size="sm"
                  icon={<Pencil className="w-3.5 h-3.5" />}
                  onClick={() => navigate(`/w/${workspaceId}/ideas/${ideaId}/edit`)}
                >
                  <span className="hidden sm:inline">편집</span>
                </Button>
              )}
              {canDelete && (
                <Button variant="icon" title="삭제" onClick={() => setDeleteOpen(true)}>
                  <Trash2 className="w-4 h-4 text-[#dc2626]" />
                </Button>
              )}
              <Button variant="ai" size="sm" icon={<Sparkles className="w-3.5 h-3.5" />} onClick={() => setAiDrawer(true)}>
                <span className="hidden sm:inline">AI로 발전시키기</span>
              </Button>
              <Button variant="icon"><MoreHorizontal className="w-4 h-4" /></Button>
            </div>
          </div>

          <div className="flex flex-wrap gap-4 mt-4 pt-4 border-t border-[rgba(0,0,0,0.05)]">
            <MetaItem label="분야" value={idea.category?.name ?? "—"} />
            <MetaItem label="우선순위" value={<ApiPriorityBadge priority={idea.priority} />} />
            <MetaItem label="구현 가능성" value={<ApiFeasibilityBadge feasibility={idea.feasibility} />} />
            <MetaItem label="공개 범위" value={<ApiVisibilityBadge visibility={idea.visibility} />} />
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
            {idea.next_review_date && (
              <MetaItem label="다음 검토일" value={idea.next_review_date} />
            )}
          </div>

          <div className="flex gap-0.5 mt-4 -mb-px">
            {TABS.map((t) => (
              <button
                key={t.id}
                type="button"
                onClick={() => setTab(t.id)}
                className={clsx(
                  "flex items-center gap-1.5 px-3 py-2 text-sm font-medium border-b-2 transition-colors",
                  tab === t.id ? "border-[#4f46e5] text-[#4f46e5]" : "border-transparent text-[#6b6b80] hover:text-[#111118]",
                )}
              >
                <t.icon className="w-3.5 h-3.5" />
                {t.label}
              </button>
            ))}
          </div>
        </div>

        <div className="flex-1 overflow-y-auto px-4 sm:px-8 py-6">
          {tab === "overview" && (
            <div className="max-w-2xl space-y-6">
              {sections.map((s) =>
                s.value ? (
                  <div key={s.label}>
                    <h4 className="text-xs font-semibold text-[#6b6b80] uppercase tracking-wider mb-2">{s.label}</h4>
                    <p className="text-sm text-[#111118] leading-relaxed whitespace-pre-wrap">{s.value}</p>
                  </div>
                ) : null,
              )}
              {sections.every((s) => !s.value) && (
                <p className="text-sm text-[#6b6b80]">등록된 상세 내용이 없습니다.</p>
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
                  <p className="text-sm font-semibold text-[#111118] mb-2">{ev.title}</p>
                  <p className="text-xs text-[#6b6b80] mb-2">{ev.publisher} · {ev.publishedAt}</p>
                  <p className="text-sm text-[#111118] leading-relaxed mb-3">{ev.summary}</p>
                </div>
              ))}
            </div>
          )}

          {tab === "discussion" && (
            <div className="max-w-xl">
              <p className="text-sm text-[#6b6b80] mb-4">댓글 기능은 추후 제공됩니다.</p>
              <div className="flex gap-3 pt-2 border-t border-[rgba(0,0,0,0.06)]">
                <Avatar user={author} size="sm" />
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
              <div className="flex gap-3 pb-6">
                <div className="w-7 h-7 rounded-full bg-[#f0f0f5] border border-white flex items-center justify-center shrink-0">
                  <FileText className="w-3.5 h-3.5 text-[#16a34a]" />
                </div>
                <div>
                  <p className="text-sm text-[#111118]">아이디어 등록</p>
                  <p className="text-xs text-[#9ca3af] mt-0.5">
                    {author.name} · {new Date(idea.created_at).toLocaleString("ko")}
                  </p>
                </div>
              </div>
            </div>
          )}
        </div>
      </div>

      {aiDrawer && (
        <div className="fixed right-0 top-16 bottom-0 w-80 bg-white border-l border-[rgba(0,0,0,0.08)] shadow-xl z-30 flex flex-col">
          <div className="flex items-center justify-between px-5 py-4 border-b border-[rgba(0,0,0,0.06)]">
            <div className="flex items-center gap-2">
              <Sparkles className="w-4 h-4 text-[#7c3aed]" />
              <p className="text-sm font-semibold text-[#111118]">AI로 발전시키기</p>
            </div>
            <button type="button" onClick={() => setAiDrawer(false)} className="w-7 h-7 flex items-center justify-center rounded-lg text-[#6b6b80] hover:bg-[#f4f4f8]">
              <X className="w-4 h-4" />
            </button>
          </div>
          <div className="flex-1 overflow-y-auto p-4">
            <p className="text-xs text-[#6b6b80] mb-3">발전 방향을 선택하세요. (Step 8에서 실제 AI 연동 예정)</p>
            <div className="space-y-2">
              {AI_EVOLVE_OPTIONS.map((opt) => (
                <button key={opt} type="button" className="w-full text-left px-3 py-2.5 rounded-lg border border-[rgba(0,0,0,0.08)] hover:border-[#7c3aed]/30 hover:bg-[#f5f3ff] text-sm text-[#111118]">
                  {opt}
                </button>
              ))}
            </div>
          </div>
        </div>
      )}

      <ConfirmDialog
        open={deleteOpen}
        onClose={() => setDeleteOpen(false)}
        onConfirm={() => void handleDelete()}
        title="아이디어를 삭제하시겠습니까?"
        description="삭제된 아이디어는 복구할 수 없습니다."
        confirmLabel={deleting ? "삭제 중..." : "삭제"}
        variant="danger"
      />
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
