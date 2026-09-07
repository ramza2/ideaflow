import { useEffect, useRef, useState } from "react";
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
  ClipboardCheck,
  FlaskConical,
  AtSign,
  Loader2,
} from "lucide-react";
import {
  createIdeaRefineSession,
  createIdeaResearchSession,
  getLatestIdeaResearchSession,
} from "../../api/aiSessions";
import { deleteIdea, getIdea } from "../../api/ideas";
import {
  approveWebResearch,
  cancelWebResearch,
  getIdeaEvidence,
  previewWebResearch,
  retryWebResearchRun,
} from "../../api/webResearch";
import {
  createComment,
  deleteComment,
  listComments,
  listMentionCandidates,
  updateComment,
} from "../../api/comments";
import { createReviewRequest, listEligibleReviewers } from "../../api/reviews";
import { ApiError, apiErrorMessage } from "../../api/client";
import { useWebResearch } from "../../ai/useWebResearch";
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
import { WebSearchApprovalPanel } from "../../components/ai/WebSearchApprovalPanel";
import { IdeaValidationPanel } from "../../components/ideas/IdeaValidationPanel";
import { useAuth } from "../../auth/AuthProvider";
import { useWorkspace } from "../../workspace/WorkspaceProvider";
import { toDisplayUser } from "../../utils/avatar";
import { REVIEW_KIND_OPTIONS, dispatchReviewCountsChanged } from "../../utils/collaboration";
import { REFINE_DIRECTION_OPTIONS } from "../../utils/refineDirection";
import type {
  AiSession,
  IdeaComment,
  IdeaDetail,
  IdeaEvidenceItem,
  IdeaRefineDirection,
  StageRef,
  UserRef,
  WebResearchRun,
} from "../../types/api";

type DetailTab = "overview" | "research" | "validation" | "discussion" | "history";

const AI_EVOLVE_OPTIONS: { direction: IdeaRefineDirection; label: string }[] =
  REFINE_DIRECTION_OPTIONS;

function formatFetchedAt(value: string): string {
  const d = new Date(value);
  if (Number.isNaN(d.getTime())) return value;
  const y = d.getFullYear();
  const m = String(d.getMonth() + 1).padStart(2, "0");
  const day = String(d.getDate()).padStart(2, "0");
  const hh = String(d.getHours()).padStart(2, "0");
  const mm = String(d.getMinutes()).padStart(2, "0");
  return `${y}.${m}.${day} ${hh}:${mm}`;
}

function researchStatusLabel(status: string | null | undefined): string | null {
  switch (status) {
    case "QUEUED":
      return "검색 준비 중";
    case "SEARCHING":
      return "웹 자료 검색 중";
    case "REFINING":
      return "검색 결과를 근거 자료로 정리 중";
    case "READY":
      return "조사 완료";
    case "FAILED":
      return "조사 실패";
    default:
      return null;
  }
}

export function IdeaDetailPage() {
  const navigate = useNavigate();
  const { user } = useAuth();
  const { currentWorkspace } = useWorkspace();
  const { workspaceId = "", ideaId = "" } = useParams();
  const [searchParams, setSearchParams] = useSearchParams();
  const tabParam = (searchParams.get("tab") as DetailTab) || "overview";
  const tab = tabParam;

  const [idea, setIdea] = useState<IdeaDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [aiDrawer, setAiDrawer] = useState(false);
  const [refiningDirection, setRefiningDirection] = useState<IdeaRefineDirection | null>(null);
  const [deleteOpen, setDeleteOpen] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const [evidence, setEvidence] = useState<IdeaEvidenceItem[]>([]);
  const [evidenceLoading, setEvidenceLoading] = useState(false);
  const [evidenceError, setEvidenceError] = useState<string | null>(null);

  const [researchSessionId, setResearchSessionId] = useState<string | null>(null);
  const [researchSession, setResearchSession] = useState<AiSession | null>(null);
  const [researchPanelOpen, setResearchPanelOpen] = useState(false);
  const [researchQueries, setResearchQueries] = useState<string[]>([]);
  const [previewRun, setPreviewRun] = useState<WebResearchRun | null>(null);
  const [loadingPreview, setLoadingPreview] = useState(false);
  const [approvingResearch, setApprovingResearch] = useState(false);
  const [researchError, setResearchError] = useState<string | null>(null);
  const [startingResearch, setStartingResearch] = useState(false);
  const [researchNotice, setResearchNotice] = useState<string | null>(null);
  const [lastCompletedRunId, setLastCompletedRunId] = useState<string | null>(null);
  const researchApprovalInFlightRef = useRef(false);
  const submittedResearchRunIdRef = useRef<string | null>(null);

  const [comments, setComments] = useState<IdeaComment[]>([]);
  const [commentsLoading, setCommentsLoading] = useState(false);
  const [commentsError, setCommentsError] = useState<string | null>(null);
  const [commentBody, setCommentBody] = useState("");
  const [mentionCandidates, setMentionCandidates] = useState<UserRef[]>([]);
  const [selectedMentions, setSelectedMentions] = useState<UserRef[]>([]);
  const [mentionOpen, setMentionOpen] = useState(false);
  const [postingComment, setPostingComment] = useState(false);
  const [editingCommentId, setEditingCommentId] = useState<string | null>(null);
  const [editingBody, setEditingBody] = useState("");

  const [reviewModalOpen, setReviewModalOpen] = useState(false);
  const [eligibleReviewers, setEligibleReviewers] = useState<UserRef[]>([]);
  const [reviewersLoading, setReviewersLoading] = useState(false);
  const [reviewerId, setReviewerId] = useState("");
  const [reviewKind, setReviewKind] = useState<"GENERAL" | "NEEDS_INFO" | "NEXT_STAGE">("GENERAL");
  const [reviewMessage, setReviewMessage] = useState("");
  const [reviewDueDate, setReviewDueDate] = useState("");
  const [submittingReview, setSubmittingReview] = useState(false);

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

  useEffect(() => {
    if (!workspaceId || !ideaId || tab !== "research") return;
    let cancelled = false;
    setEvidenceLoading(true);
    setEvidenceError(null);
    void getIdeaEvidence(workspaceId, ideaId)
      .then((data) => {
        if (!cancelled) setEvidence(data.items);
      })
      .catch((err) => {
        if (!cancelled) {
          setEvidenceError(apiErrorMessage(err, "근거를 불러오지 못했습니다."));
          setEvidence([]);
        }
      })
      .finally(() => {
        if (!cancelled) setEvidenceLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [workspaceId, ideaId, tab]);

  // Recover in-progress / awaiting RESEARCH session after reload.
  useEffect(() => {
    if (!workspaceId || !ideaId || tab !== "research") return;
    let cancelled = false;
    void getLatestIdeaResearchSession(workspaceId, ideaId)
      .then(async (data) => {
        if (cancelled || !data.session) return;
        setResearchSessionId(data.session.id);
        setResearchSession(data.session);
        setResearchQueries(
          (data.session.research_topics ?? []).filter(Boolean).slice(0, 5),
        );
      })
      .catch(() => {
        // Ignore recovery errors; user can still start a new research.
      });
    return () => {
      cancelled = true;
    };
  }, [workspaceId, ideaId, tab]);

  const {
    run: researchRun,
    inProgress: researchInProgress,
    refresh: refreshResearch,
  } = useWebResearch(workspaceId, researchSessionId ?? undefined, {
    enabled: Boolean(workspaceId && researchSessionId),
  });

  useEffect(() => {
    if (!researchRun || !workspaceId || !ideaId) return;
    if (researchRun.status !== "READY") return;
    if (lastCompletedRunId === researchRun.id) return;
    setLastCompletedRunId(researchRun.id);
    void getIdeaEvidence(workspaceId, ideaId)
      .then((data) => {
        setEvidence(data.items);
        if ((researchRun.result_count ?? 0) === 0) {
          toast.info("검색은 완료되었지만 새 근거 자료를 찾지 못했습니다.");
          setResearchNotice("검색은 완료되었지만 새 근거 자료를 찾지 못했습니다.");
        } else {
          toast.success("조사가 완료되었습니다.", "새 근거 자료를 확인해 주세요.");
          setResearchNotice(null);
        }
      })
      .catch(() => {
        toast.success("조사가 완료되었습니다.");
      });
  }, [researchRun, workspaceId, ideaId, lastCompletedRunId]);

  // Re-open approval panel when recovering AWAITING_APPROVAL (reload recovery).
  // Do not reopen a run that this tab just submitted for approval (stale AWAITING).
  useEffect(() => {
    if (!researchRun || researchPanelOpen || startingResearch) return;
    if (researchRun.status !== "AWAITING_APPROVAL") return;
    if (submittedResearchRunIdRef.current === researchRun.id) return;
    setPreviewRun(researchRun);
    if (researchRun.queries_to_send?.length) {
      setResearchQueries(researchRun.queries_to_send);
    }
    setResearchPanelOpen(true);
  }, [researchRun, researchPanelOpen, startingResearch]);

  // Once a run leaves AWAITING_APPROVAL, never keep the approval modal open.
  useEffect(() => {
    if (!researchRun || researchRun.status === "AWAITING_APPROVAL") return;
    if (submittedResearchRunIdRef.current === researchRun.id) {
      submittedResearchRunIdRef.current = null;
    }
    if (researchPanelOpen) {
      setResearchPanelOpen(false);
    }
    setPreviewRun((current) => (current?.id === researchRun.id ? null : current));
    setResearchError(null);
  }, [researchRun, researchPanelOpen]);

  useEffect(() => {
    if (!workspaceId || !ideaId || tab !== "discussion") return;
    let cancelled = false;
    setCommentsLoading(true);
    setCommentsError(null);
    void listComments(workspaceId, ideaId)
      .then((data) => {
        if (!cancelled) setComments(data.items);
      })
      .catch((err) => {
        if (!cancelled) {
          setCommentsError(apiErrorMessage(err, "댓글을 불러오지 못했습니다."));
          setComments([]);
        }
      })
      .finally(() => {
        if (!cancelled) setCommentsLoading(false);
      });
    void listMentionCandidates(workspaceId, ideaId)
      .then((data) => {
        if (!cancelled) setMentionCandidates(data.items);
      })
      .catch(() => {
        if (!cancelled) setMentionCandidates([]);
      });
    return () => {
      cancelled = true;
    };
  }, [workspaceId, ideaId, tab]);

  async function openReviewModal() {
    if (!workspaceId || !ideaId) return;
    setReviewModalOpen(true);
    setReviewersLoading(true);
    setReviewerId("");
    setReviewKind("GENERAL");
    setReviewMessage("");
    setReviewDueDate("");
    try {
      const data = await listEligibleReviewers(workspaceId, ideaId);
      setEligibleReviewers(data.items);
    } catch (err) {
      toast.error(apiErrorMessage(err, "검토자 목록을 불러오지 못했습니다."));
      setEligibleReviewers([]);
    } finally {
      setReviewersLoading(false);
    }
  }

  async function handleSubmitReview() {
    if (!workspaceId || !ideaId || !reviewerId) return;
    setSubmittingReview(true);
    try {
      await createReviewRequest(workspaceId, ideaId, {
        reviewer_id: reviewerId,
        kind: reviewKind,
        message: reviewMessage.trim() || null,
        due_date: reviewDueDate || null,
      });
      toast.success("검토를 요청했습니다.");
      setReviewModalOpen(false);
      dispatchReviewCountsChanged();
    } catch (err) {
      toast.error(apiErrorMessage(err, "검토 요청에 실패했습니다."));
    } finally {
      setSubmittingReview(false);
    }
  }

  function toggleMention(candidate: UserRef) {
    setSelectedMentions((prev) => {
      const exists = prev.some((m) => m.id === candidate.id);
      if (exists) return prev.filter((m) => m.id !== candidate.id);
      if (prev.length >= 20) {
        toast.error("한 댓글에 최대 20명까지 언급할 수 있습니다.");
        return prev;
      }
      return [...prev, candidate];
    });
  }

  async function handlePostComment() {
    if (!workspaceId || !ideaId || !commentBody.trim()) return;
    setPostingComment(true);
    try {
      const created = await createComment(workspaceId, ideaId, {
        body: commentBody.trim(),
        mention_user_ids: selectedMentions.map((m) => m.id),
      });
      setComments((prev) => [...prev, created]);
      setCommentBody("");
      setSelectedMentions([]);
      setMentionOpen(false);
    } catch (err) {
      toast.error(apiErrorMessage(err, "댓글 게시에 실패했습니다."));
    } finally {
      setPostingComment(false);
    }
  }

  async function handleSaveEdit(commentId: string) {
    if (!workspaceId || !ideaId || !editingBody.trim()) return;
    try {
      const updated = await updateComment(workspaceId, ideaId, commentId, {
        body: editingBody.trim(),
      });
      setComments((prev) => prev.map((c) => (c.id === commentId ? updated : c)));
      setEditingCommentId(null);
      setEditingBody("");
    } catch (err) {
      toast.error(apiErrorMessage(err, "댓글 수정에 실패했습니다."));
    }
  }

  async function handleDeleteComment(commentId: string) {
    if (!workspaceId || !ideaId) return;
    try {
      await deleteComment(workspaceId, ideaId, commentId);
      setComments((prev) => prev.filter((c) => c.id !== commentId));
    } catch (err) {
      toast.error(apiErrorMessage(err, "댓글 삭제에 실패했습니다."));
    }
  }

  function handleShare() {
    navigator.clipboard?.writeText(window.location.href).catch(() => {});
    toast.success("링크가 복사되었습니다");
  }

  async function handleStartRefine(direction: IdeaRefineDirection) {
    if (!workspaceId || !ideaId || refiningDirection) return;
    setRefiningDirection(direction);
    try {
      const session = await createIdeaRefineSession(workspaceId, ideaId, { direction });
      setAiDrawer(false);
      navigate(`/w/${workspaceId}/ideas/${ideaId}/ai/refine/${session.id}/analyzing`);
    } catch (err) {
      toast.error(apiErrorMessage(err, "AI 발전 요청을 시작하지 못했습니다."));
    } finally {
      setRefiningDirection(null);
    }
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
  const allowWebSearch = currentWorkspace?.effective_allow_web_search !== false;
  const canStartResearch = canEdit && allowWebSearch;
  const ideaTitle = idea.title;
  const author = toDisplayUser(idea.author);
  const assignee = idea.assignee ? toDisplayUser(idea.assignee) : null;

  async function handleStartResearch() {
    if (!workspaceId || !ideaId || !canStartResearch || startingResearch) return;
    if (researchInProgress) {
      toast.error("이 아이디어에 대한 웹 조사가 이미 진행 중입니다.");
      return;
    }
    submittedResearchRunIdRef.current = null;
    researchApprovalInFlightRef.current = false;
    setStartingResearch(true);
    setResearchError(null);
    setResearchNotice(null);
    try {
      // Recover existing awaiting-approval run instead of creating a stuck preview.
      if (researchSessionId && researchRun?.status === "AWAITING_APPROVAL") {
        setPreviewRun(researchRun);
        setResearchQueries(
          researchRun.queries_to_send?.length
            ? researchRun.queries_to_send
            : researchQueries,
        );
        setResearchPanelOpen(true);
        return;
      }
      const session = await createIdeaResearchSession(workspaceId, ideaId);
      setResearchSessionId(session.id);
      setResearchSession(session);
      const topics = (session.research_topics ?? []).filter(Boolean).slice(0, 5);
      setResearchQueries(topics.length > 0 ? topics : ideaTitle ? [ideaTitle] : [""]);
      setPreviewRun(null);
      setResearchPanelOpen(true);
    } catch (err) {
      toast.error(apiErrorMessage(err, "다시 조사를 시작하지 못했습니다."));
    } finally {
      setStartingResearch(false);
    }
  }

  function clearResearchControlState() {
    submittedResearchRunIdRef.current = null;
    researchApprovalInFlightRef.current = false;
    setResearchPanelOpen(false);
    setPreviewRun(null);
    setResearchSessionId(null);
    setResearchSession(null);
    setResearchError(null);
    setResearchNotice(null);
  }

  function handleResearchSourceChanged() {
    clearResearchControlState();
    toast.info(
      "아이디어 내용이 변경되었습니다. 최신 내용으로 다시 조사를 시작해 주세요.",
    );
  }

  async function handleResearchPreview() {
    if (!workspaceId || !researchSessionId || loadingPreview) return;
    const queries = researchQueries.map((q) => q.trim()).filter(Boolean);
    if (queries.length === 0) return;
    setLoadingPreview(true);
    setResearchError(null);
    try {
      const draft =
        (researchSession?.source_idea_snapshot as Record<string, unknown> | null) ??
        (researchSession?.draft as Record<string, unknown> | null) ??
        {};
      const run = await previewWebResearch(workspaceId, researchSessionId, {
        queries,
        current_draft: draft,
        user_edited_fields: [],
      });
      setPreviewRun(run);
      await refreshResearch();
    } catch (err) {
      if (err instanceof ApiError && err.code === "IDEA_RESEARCH_SOURCE_CHANGED") {
        handleResearchSourceChanged();
        return;
      }
      setResearchError(apiErrorMessage(err, "검색어 미리보기에 실패했습니다."));
    } finally {
      setLoadingPreview(false);
    }
  }

  async function handleResearchApprove() {
    if (
      !workspaceId ||
      !researchSessionId ||
      !previewRun ||
      approvingResearch ||
      researchApprovalInFlightRef.current
    ) {
      return;
    }

    const runId = previewRun.id;
    researchApprovalInFlightRef.current = true;
    submittedResearchRunIdRef.current = runId;
    setApprovingResearch(true);
    setResearchError(null);
    try {
      const approvedRun = await approveWebResearch(workspaceId, researchSessionId, runId);
      setResearchPanelOpen(false);
      setPreviewRun(null);
      setResearchError(null);
      // Prefer server status when available; suppression still blocks stale AWAITING reopen.
      if (approvedRun.status !== "AWAITING_APPROVAL") {
        // Keep submittedResearchRunIdRef until researchRun catches up, then cleanup effect clears it.
      }
      await refreshResearch();
      toast.info("웹 검색을 시작합니다", "검색 결과는 근거 자료에 추가됩니다.");
    } catch (err) {
      // Approval did not succeed — allow retry / recovery of this run.
      submittedResearchRunIdRef.current = null;
      if (err instanceof ApiError && err.code === "IDEA_RESEARCH_SOURCE_CHANGED") {
        handleResearchSourceChanged();
        return;
      }
      setResearchError(apiErrorMessage(err, "검색 승인에 실패했습니다."));
    } finally {
      researchApprovalInFlightRef.current = false;
      setApprovingResearch(false);
    }
  }

  async function handleResearchCancel() {
    if (
      previewRun?.status === "AWAITING_APPROVAL" &&
      workspaceId &&
      researchSessionId
    ) {
      try {
        await cancelWebResearch(workspaceId, researchSessionId, previewRun.id);
      } catch {
        // ignore cancel errors on close
      }
    }
    if (previewRun && submittedResearchRunIdRef.current === previewRun.id) {
      submittedResearchRunIdRef.current = null;
    }
    setResearchPanelOpen(false);
    setPreviewRun(null);
    setResearchError(null);
    await refreshResearch();
  }

  async function handleEditResearchQueries() {
    if (!previewRun || !workspaceId || !researchSessionId) return;
    setResearchError(null);
    try {
      await cancelWebResearch(workspaceId, researchSessionId, previewRun.id);
      if (submittedResearchRunIdRef.current === previewRun.id) {
        submittedResearchRunIdRef.current = null;
      }
      setPreviewRun(null);
      await refreshResearch();
    } catch (err) {
      setResearchError(
        apiErrorMessage(err, "검색어 수정을 위해 기존 미리보기를 취소하지 못했습니다."),
      );
      throw err;
    }
  }

  async function handleResearchRetry() {
    if (!workspaceId || !researchSessionId || !researchRun) return;
    try {
      await retryWebResearchRun(workspaceId, researchSessionId, researchRun.id);
      setResearchNotice(null);
      await refreshResearch();
      toast.info("웹 조사를 다시 시도합니다.");
    } catch (err) {
      if (err instanceof ApiError && err.code === "IDEA_RESEARCH_SOURCE_CHANGED") {
        handleResearchSourceChanged();
        return;
      }
      toast.error(apiErrorMessage(err, "다시 시도에 실패했습니다."));
    }
  }

  const TABS: { id: DetailTab; label: string; icon: typeof FileText }[] = [
    { id: "overview", label: "개요", icon: FileText },
    { id: "research", label: "조사 및 근거", icon: BookOpen },
    { id: "validation", label: "검증", icon: FlaskConical },
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
              <Button
                variant="icon"
                title="즐겨찾기 기능은 추후 제공됩니다"
                onClick={() => toast.info("즐겨찾기 기능은 추후 제공됩니다")}
              >
                <Star className="w-4 h-4" />
              </Button>
              <Button variant="icon" title="공유" onClick={handleShare} className="hidden sm:flex"><Share2 className="w-4 h-4" /></Button>
              {canEdit && (
                <Button
                  variant="secondary"
                  size="sm"
                  icon={<ClipboardCheck className="w-3.5 h-3.5" />}
                  onClick={() => void openReviewModal()}
                >
                  <span className="hidden sm:inline">검토 요청</span>
                </Button>
              )}
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
              {canEdit && (
                <Button variant="ai" size="sm" icon={<Sparkles className="w-3.5 h-3.5" />} onClick={() => setAiDrawer(true)}>
                  <span className="hidden sm:inline">AI로 발전시키기</span>
                </Button>
              )}
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
                {canEdit && (
                  <Button
                    variant="ghost"
                    size="sm"
                    icon={
                      startingResearch ? (
                        <Loader2 className="w-3.5 h-3.5 animate-spin" />
                      ) : (
                        <RefreshCw className="w-3.5 h-3.5" />
                      )
                    }
                    disabled={!canStartResearch || startingResearch || researchInProgress}
                    title={
                      !allowWebSearch
                        ? "이 작업공간에서는 웹 검색이 비활성화되어 있습니다."
                        : researchInProgress
                          ? "웹 조사가 진행 중입니다."
                          : undefined
                    }
                    onClick={() => void handleStartResearch()}
                  >
                    다시 조사
                  </Button>
                )}
              </div>

              {(researchInProgress ||
                researchRun?.status === "FAILED" ||
                researchRun?.status === "READY" ||
                researchNotice) && (
                <div className="rounded-xl border border-[rgba(0,0,0,0.08)] bg-white px-4 py-3 flex items-center gap-3">
                  {researchInProgress && (
                    <Loader2 className="w-4 h-4 animate-spin text-[#2563eb] shrink-0" />
                  )}
                  <div className="flex-1 min-w-0">
                    <p className="text-sm text-[#111118]">
                      {researchNotice ??
                        researchStatusLabel(researchRun?.status) ??
                        (researchInProgress ? "조사 진행 중" : null)}
                    </p>
                    {researchRun?.status === "FAILED" && (
                      <p className="text-xs text-[#dc2626] mt-1">
                        {researchRun.failure?.message || "웹 조사에 실패했습니다."}
                      </p>
                    )}
                    {researchRun?.status === "READY" && researchRun.research_summary && (
                      <p className="text-xs text-[#6b6b80] mt-1 whitespace-pre-wrap">
                        최근 조사 요약: {researchRun.research_summary}
                      </p>
                    )}
                  </div>
                  {researchRun?.status === "FAILED" && (
                    <Button
                      variant="secondary"
                      size="sm"
                      onClick={() => void handleResearchRetry()}
                    >
                      다시 시도
                    </Button>
                  )}
                </div>
              )}

              {evidenceLoading && (
                <p className="text-sm text-[#6b6b80]">근거를 불러오는 중...</p>
              )}
              {evidenceError && (
                <p className="text-sm text-[#dc2626]">{evidenceError}</p>
              )}
              {!evidenceLoading && !evidenceError && evidence.length === 0 && (
                <p className="text-sm text-[#6b6b80]">등록된 외부 검색 근거가 없습니다.</p>
              )}
              {evidence.map((ev) => (
                <div key={ev.id} className="bg-white rounded-xl border border-[rgba(0,0,0,0.07)] p-4">
                  <a
                    href={ev.url}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="text-sm font-semibold text-[#2563eb] hover:underline"
                  >
                    {ev.title}
                  </a>
                  <p className="text-xs text-[#6b6b80] mb-2">
                    {[ev.source_name, ev.domain].filter(Boolean).join(" · ")}
                    {ev.published_at
                      ? ` · 게시 ${new Date(ev.published_at).toLocaleDateString("ko")}`
                      : ""}
                    {ev.fetched_at ? ` · 수집 ${formatFetchedAt(ev.fetched_at)}` : ""}
                  </p>
                  {ev.snippet && (
                    <p className="text-sm text-[#111118] leading-relaxed whitespace-pre-wrap mb-2">
                      {ev.snippet}
                    </p>
                  )}
                  {ev.related_fields.length > 0 && (
                    <p className="text-xs text-[#9ca3af]">
                      관련 필드: {ev.related_fields.join(", ")}
                    </p>
                  )}
                </div>
              ))}
            </div>
          )}

          {tab === "validation" && (
            <IdeaValidationPanel
              workspaceId={workspaceId}
              idea={idea}
              canEdit={canEdit}
              onIdeaStageChange={(stage: StageRef) => {
                setIdea((prev) => (prev ? { ...prev, stage } : prev));
              }}
            />
          )}

          {tab === "discussion" && (
            <div className="max-w-xl">
              {commentsLoading ? (
                <p className="text-sm text-[#6b6b80] mb-4">댓글을 불러오는 중...</p>
              ) : commentsError ? (
                <p className="text-sm text-[#dc2626] mb-4">{commentsError}</p>
              ) : comments.length === 0 ? (
                <p className="text-sm text-[#6b6b80] mb-4">아직 댓글이 없습니다. 첫 댓글을 남겨보세요.</p>
              ) : (
                <div className="space-y-4 mb-6">
                  {comments.map((c) => {
                    const commentAuthor = toDisplayUser(c.author);
                    const isEditing = editingCommentId === c.id;
                    return (
                      <div key={c.id} className="flex gap-3">
                        <Avatar user={commentAuthor} size="sm" />
                        <div className="flex-1 min-w-0">
                          <div className="flex items-center gap-2 mb-1">
                            <span className="text-sm font-medium text-[#111118]">{commentAuthor.name}</span>
                            <span className="text-xs text-[#9ca3af]">
                              {new Date(c.created_at).toLocaleString("ko")}
                              {c.edited ? " (수정됨)" : ""}
                            </span>
                          </div>
                          {isEditing ? (
                            <div>
                              <textarea
                                value={editingBody}
                                onChange={(e) => setEditingBody(e.target.value)}
                                className="w-full h-20 rounded-lg border border-[rgba(0,0,0,0.1)] bg-white px-3 py-2 text-sm resize-none focus:outline-none focus:ring-2 focus:ring-[#4f46e5]/20"
                              />
                              <div className="flex gap-2 mt-2">
                                <Button variant="ghost" size="sm" onClick={() => setEditingCommentId(null)}>
                                  취소
                                </Button>
                                <Button variant="primary" size="sm" onClick={() => void handleSaveEdit(c.id)}>
                                  저장
                                </Button>
                              </div>
                            </div>
                          ) : (
                            <>
                              <p className="text-sm text-[#111118] whitespace-pre-wrap">{c.body}</p>
                              {c.mentions.length > 0 && (
                                <div className="flex flex-wrap gap-1 mt-2">
                                  {c.mentions.map((m) => (
                                    <span
                                      key={m.id}
                                      className="text-xs px-2 py-0.5 rounded-full bg-[#ede9fe] text-[#4f46e5]"
                                    >
                                      @{m.name}
                                    </span>
                                  ))}
                                </div>
                              )}
                            </>
                          )}
                          {!isEditing && (c.can_edit || c.can_delete) && (
                            <div className="flex gap-2 mt-2">
                              {c.can_edit && (
                                <button
                                  type="button"
                                  className="text-xs text-[#6b6b80] hover:text-[#4f46e5]"
                                  onClick={() => {
                                    setEditingCommentId(c.id);
                                    setEditingBody(c.body);
                                  }}
                                >
                                  수정
                                </button>
                              )}
                              {c.can_delete && (
                                <button
                                  type="button"
                                  className="text-xs text-[#dc2626] hover:underline"
                                  onClick={() => void handleDeleteComment(c.id)}
                                >
                                  삭제
                                </button>
                              )}
                            </div>
                          )}
                        </div>
                      </div>
                    );
                  })}
                </div>
              )}
              <div className="flex gap-3 pt-2 border-t border-[rgba(0,0,0,0.06)]">
                <Avatar
                  user={user ? toDisplayUser({ id: user.id, name: user.name, email: user.email }) : author}
                  size="sm"
                />
                <div className="flex-1">
                  <textarea
                    value={commentBody}
                    onChange={(e) => setCommentBody(e.target.value)}
                    placeholder="의견을 남겨보세요"
                    className="w-full h-20 rounded-lg border border-[rgba(0,0,0,0.1)] bg-white px-3 py-2 text-sm resize-none focus:outline-none focus:ring-2 focus:ring-[#4f46e5]/20 focus:border-[#4f46e5]"
                  />
                  {selectedMentions.length > 0 && (
                    <div className="flex flex-wrap gap-1 mt-2">
                      {selectedMentions.map((m) => (
                        <span
                          key={m.id}
                          className="text-xs px-2 py-0.5 rounded-full bg-[#ede9fe] text-[#4f46e5] flex items-center gap-1"
                        >
                          @{m.name}
                          <button type="button" onClick={() => toggleMention(m)} className="hover:text-[#dc2626]">
                            ×
                          </button>
                        </span>
                      ))}
                    </div>
                  )}
                  <div className="flex items-center justify-between mt-2">
                    <div className="relative">
                      <Button
                        variant="ghost"
                        size="sm"
                        icon={<AtSign className="w-3.5 h-3.5" />}
                        onClick={() => setMentionOpen(!mentionOpen)}
                      >
                        사용자 언급
                      </Button>
                      {mentionOpen && mentionCandidates.length > 0 && (
                        <div className="absolute bottom-full left-0 mb-1 w-56 bg-white rounded-xl border border-[rgba(0,0,0,0.08)] shadow-lg py-1 z-10 max-h-40 overflow-y-auto">
                          {mentionCandidates
                            .filter((m) => m.id !== user?.id)
                            .map((m) => (
                              <button
                                key={m.id}
                                type="button"
                                onClick={() => toggleMention(m)}
                                className={clsx(
                                  "w-full text-left px-3 py-2 text-sm hover:bg-[#f4f4f8]",
                                  selectedMentions.some((s) => s.id === m.id) && "text-[#4f46e5]",
                                )}
                              >
                                {m.name}
                              </button>
                            ))}
                        </div>
                      )}
                    </div>
                    <Button
                      variant="primary"
                      size="sm"
                      icon={<Send className="w-3.5 h-3.5" />}
                      loading={postingComment}
                      disabled={postingComment || !commentBody.trim()}
                      onClick={() => void handlePostComment()}
                    >
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

      {canEdit && aiDrawer && (
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
            <p className="text-xs text-[#6b6b80] mb-3">발전 방향을 선택하세요.</p>
            <div className="space-y-2">
              {AI_EVOLVE_OPTIONS.map((opt) => {
                const isStarting = refiningDirection === opt.direction;
                return (
                  <button
                    key={opt.direction}
                    type="button"
                    disabled={refiningDirection !== null}
                    onClick={() => void handleStartRefine(opt.direction)}
                    className={clsx(
                      "w-full text-left px-3 py-2.5 rounded-lg border border-[rgba(0,0,0,0.08)] text-sm text-[#111118] flex items-center justify-between gap-2",
                      refiningDirection === null
                        ? "hover:border-[#7c3aed]/30 hover:bg-[#f5f3ff]"
                        : "opacity-60 cursor-not-allowed",
                    )}
                  >
                    {opt.label}
                    {isStarting && <Loader2 className="w-3.5 h-3.5 animate-spin text-[#7c3aed]" />}
                  </button>
                );
              })}
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

      <WebSearchApprovalPanel
        open={researchPanelOpen}
        onClose={() => void handleResearchCancel()}
        initialQueries={researchQueries}
        previewRun={previewRun}
        loadingPreview={loadingPreview}
        approving={approvingResearch}
        error={researchError}
        onQueriesChange={setResearchQueries}
        onPreview={() => void handleResearchPreview()}
        onApprove={() => void handleResearchApprove()}
        onCancel={() => void handleResearchCancel()}
        onEditQueries={handleEditResearchQueries}
        mode="REGISTERED_IDEA_RESEARCH"
      />

      {reviewModalOpen && (
        <div className="fixed inset-0 bg-black/30 z-50 flex items-center justify-center p-4">
          <div className="bg-white rounded-2xl border border-[rgba(0,0,0,0.08)] shadow-xl w-full max-w-md p-6">
            <h3 className="text-base font-bold text-[#111118] mb-4">검토 요청</h3>
            {reviewersLoading ? (
              <p className="text-sm text-[#6b6b80]">검토자 목록을 불러오는 중...</p>
            ) : eligibleReviewers.length === 0 ? (
              <p className="text-sm text-[#6b6b80] mb-4">
                현재 공개 범위에서는 검토를 요청할 수 있는 사용자가 없습니다.
              </p>
            ) : (
              <div className="space-y-4">
                <div>
                  <label className="text-sm font-medium text-[#111118] block mb-1.5">검토자</label>
                  <select
                    value={reviewerId}
                    onChange={(e) => setReviewerId(e.target.value)}
                    className="w-full h-9 rounded-lg border border-[rgba(0,0,0,0.1)] bg-white px-3 text-sm focus:outline-none focus:ring-2 focus:ring-[#4f46e5]/20"
                  >
                    <option value="">선택하세요</option>
                    {eligibleReviewers.map((r) => (
                      <option key={r.id} value={r.id}>
                        {r.name}
                      </option>
                    ))}
                  </select>
                </div>
                <div>
                  <label className="text-sm font-medium text-[#111118] block mb-1.5">검토 유형</label>
                  <select
                    value={reviewKind}
                    onChange={(e) =>
                      setReviewKind(e.target.value as "GENERAL" | "NEEDS_INFO" | "NEXT_STAGE")
                    }
                    className="w-full h-9 rounded-lg border border-[rgba(0,0,0,0.1)] bg-white px-3 text-sm focus:outline-none focus:ring-2 focus:ring-[#4f46e5]/20"
                  >
                    {REVIEW_KIND_OPTIONS.map((opt) => (
                      <option key={opt.value} value={opt.value}>
                        {opt.label}
                      </option>
                    ))}
                  </select>
                </div>
                <div>
                  <label className="text-sm font-medium text-[#111118] block mb-1.5">메시지 (선택)</label>
                  <textarea
                    value={reviewMessage}
                    onChange={(e) => setReviewMessage(e.target.value)}
                    className="w-full h-16 rounded-lg border border-[rgba(0,0,0,0.1)] bg-white px-3 py-2 text-sm resize-none focus:outline-none focus:ring-2 focus:ring-[#4f46e5]/20"
                  />
                </div>
                <div>
                  <label className="text-sm font-medium text-[#111118] block mb-1.5">검토 기한 (선택)</label>
                  <input
                    type="date"
                    value={reviewDueDate}
                    onChange={(e) => setReviewDueDate(e.target.value)}
                    className="w-full h-9 rounded-lg border border-[rgba(0,0,0,0.1)] bg-white px-3 text-sm focus:outline-none focus:ring-2 focus:ring-[#4f46e5]/20"
                  />
                </div>
              </div>
            )}
            <div className="flex gap-2 mt-5">
              <Button variant="ghost" className="flex-1" onClick={() => setReviewModalOpen(false)}>
                취소
              </Button>
              {eligibleReviewers.length > 0 && (
                <Button
                  variant="primary"
                  className="flex-1"
                  loading={submittingReview}
                  disabled={submittingReview || !reviewerId}
                  onClick={() => void handleSubmitReview()}
                >
                  요청
                </Button>
              )}
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
