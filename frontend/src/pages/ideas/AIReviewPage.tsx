import { useEffect, useMemo, useRef, useState } from "react";
import { useNavigate, useParams, useSearchParams } from "react-router";
import { clsx } from "clsx";
import {
  Sparkles,
  ChevronDown,
  ChevronUp,
  RefreshCw,
  X,
  Check,
  Pencil,
  ArrowLeft,
  Loader2,
} from "lucide-react";
import { Button } from "../../components/common/Button";
import { SourceBadge } from "../../components/common/Badge";
import { Select } from "../../components/common/Input";
import { ProgressStepper, InlineAlert } from "../../components/common/EmptyState";
import { toast } from "../../components/common/Toast";
import { confirmAiSession } from "../../api/aiSessions";
import {
  approveWebResearch,
  cancelWebResearch,
  previewWebResearch,
  retryWebResearchRun,
} from "../../api/webResearch";
import { listCategories, listMembers, listStages } from "../../api/workspaces";
import { ApiError, apiErrorMessage } from "../../api/client";
import { useAuth } from "../../auth/useAuth";
import { useWebResearch } from "../../ai/useWebResearch";
import {
  mapProvenanceSource,
  parseVisibilityParam,
  useAiSession,
} from "../../ai/useAiSession";
import { WebSearchApprovalPanel } from "../../components/ai/WebSearchApprovalPanel";
import { useWorkspace } from "../../workspace/WorkspaceProvider";
import type {
  AiDraft,
  AiFieldProvenance,
  AiSessionConfirmRequest,
  CategoryPublic,
  IdeaFeasibility,
  IdeaPriority,
  IdeaShareInput,
  IdeaSharePermission,
  IdeaVisibility,
  MemberPublic,
  StagePublic,
  WebResearchRun,
} from "../../types/api";
import type { SourceBadgeType } from "../../types";

type DraftKey = keyof AiDraft | "tags_text";

interface EditableField {
  key: DraftKey;
  label: string;
  value: string;
  source: SourceBadgeType | null;
  multiline?: boolean;
}

const TEXT_FIELDS: { key: keyof AiDraft; label: string; section: "basic" | "content" }[] = [
  { key: "title", label: "아이디어명", section: "basic" },
  { key: "one_line_definition", label: "한 줄 정의", section: "basic" },
  { key: "background", label: "배경", section: "content" },
  { key: "problem", label: "해결하려는 문제", section: "content" },
  { key: "core_concept", label: "핵심 개념", section: "content" },
  { key: "major_features", label: "주요 기능", section: "content" },
  { key: "expected_effect", label: "기대 효과", section: "content" },
  { key: "target_users", label: "예상 사용자", section: "content" },
  { key: "scenarios", label: "사용 시나리오", section: "content" },
  { key: "challenges", label: "주요 난제", section: "content" },
  { key: "minimum_validation", label: "최소 검증 방법", section: "content" },
  { key: "related_project", label: "관련 프로젝트", section: "content" },
];

function draftValue(draft: AiDraft | null, key: keyof AiDraft): string {
  if (!draft) return "";
  const v = draft[key];
  if (v == null) return "";
  if (Array.isArray(v)) return v.join(", ");
  return String(v);
}

function provenanceFor(
  fieldProvenance: Record<string, AiFieldProvenance> | null | undefined,
  key: string,
  edited: Set<string>,
): SourceBadgeType | null {
  if (edited.has(key)) return "user_edited";
  const p = fieldProvenance?.[key];
  if (!p) return null;
  const raw = p.final_source ?? p.source ?? p.original_source;
  return mapProvenanceSource(raw);
}

export function AIReviewPage() {
  const navigate = useNavigate();
  const { workspaceId = "", sessionId = "" } = useParams();
  const [searchParams] = useSearchParams();
  const initialVisibility = parseVisibilityParam(searchParams.get("visibility"));
  const { user } = useAuth();
  const { currentWorkspace } = useWorkspace();

  const { session, loading, error, refresh } = useAiSession(workspaceId, sessionId, {
    pollWhenProcessing: false,
  });

  const {
    run: researchRun,
    inProgress: researchInProgress,
    pollError: researchPollError,
    refresh: refreshResearch,
  } = useWebResearch(workspaceId, sessionId, {
    enabled: Boolean(workspaceId && sessionId),
  });

  const allowWebSearch = currentWorkspace?.effective_allow_web_search !== false;

  const [stages, setStages] = useState<StagePublic[]>([]);
  const [categories, setCategories] = useState<CategoryPublic[]>([]);
  const [members, setMembers] = useState<MemberPublic[]>([]);
  const [metaLoaded, setMetaLoaded] = useState(false);

  const [draft, setDraft] = useState<AiDraft | null>(null);
  const [editedKeys, setEditedKeys] = useState<Set<string>>(new Set());
  const [initialized, setInitialized] = useState(false);

  const [categoryId, setCategoryId] = useState("");
  const [stageId, setStageId] = useState("");
  const [priority, setPriority] = useState<IdeaPriority>("MEDIUM");
  const [feasibility, setFeasibility] = useState<IdeaFeasibility>("UNKNOWN");
  const [visibility, setVisibility] = useState<IdeaVisibility>(initialVisibility);
  const [assigneeId, setAssigneeId] = useState("");
  const [nextReviewDate, setNextReviewDate] = useState("");
  const [tagsText, setTagsText] = useState("");
  const [shares, setShares] = useState<IdeaShareInput[]>([]);

  const [editingKey, setEditingKey] = useState<DraftKey | null>(null);
  const [editValue, setEditValue] = useState("");
  const [directEditMode, setDirectEditMode] = useState(false);
  const [originalOpen, setOriginalOpen] = useState(true);
  const [showEvidence, setShowEvidence] = useState(true);
  const [showConfirmModal, setShowConfirmModal] = useState(false);
  const [isConfirming, setIsConfirming] = useState(false);
  const [confirmError, setConfirmError] = useState<string | null>(null);

  const [researchPanelOpen, setResearchPanelOpen] = useState(false);
  const [researchQueries, setResearchQueries] = useState<string[]>([]);
  const [previewRun, setPreviewRun] = useState<WebResearchRun | null>(null);
  const [loadingPreview, setLoadingPreview] = useState(false);
  const [approvingResearch, setApprovingResearch] = useState(false);
  const [researchError, setResearchError] = useState<string | null>(null);
  const lastAppliedResearchIdRef = useRef<string | null>(null);

  // Status guards
  useEffect(() => {
    if (!session || !workspaceId || !sessionId) return;
    if (session.status === "CONFIRMED" && session.result_idea_id) {
      navigate(`/w/${workspaceId}/ideas/${session.result_idea_id}`, {
        replace: true,
      });
      return;
    }
    if (
      session.status === "PROCESSING" ||
      session.status === "NEEDS_CLARIFICATION" ||
      session.status === "FAILED"
    ) {
      const vis = searchParams.get("visibility");
      const q = vis ? `?visibility=${vis}` : `?visibility=${initialVisibility}`;
      navigate(`/w/${workspaceId}/ideas/new/ai/analyzing/${sessionId}${q}`, {
        replace: true,
      });
    }
  }, [
    session,
    workspaceId,
    sessionId,
    navigate,
    searchParams,
    initialVisibility,
  ]);

  useEffect(() => {
    if (!workspaceId) return;
    let cancelled = false;
    void Promise.all([
      listStages(workspaceId),
      listCategories(workspaceId),
      listMembers(workspaceId),
    ])
      .then(([s, c, m]) => {
        if (cancelled) return;
        setStages(s);
        setCategories(c);
        setMembers(m);
        setMetaLoaded(true);
      })
      .catch(() => {
        if (!cancelled) {
          toast.error("양식 데이터를 불러오지 못했습니다.");
          setMetaLoaded(true);
        }
      });
    return () => {
      cancelled = true;
    };
  }, [workspaceId]);

  // Initialize form from session draft once
  useEffect(() => {
    if (!session || session.status !== "READY_FOR_REVIEW") return;
    if (!metaLoaded || initialized) return;

    const d = session.draft ?? {};
    setDraft({ ...d });
    setTagsText((d.tags ?? []).join(", "));

    const slug = d.category_slug?.trim();
    if (slug) {
      const match = categories.find((c) => c.slug === slug);
      setCategoryId(match?.id ?? "");
    } else {
      setCategoryId("");
    }

    const defaultStage = stages.find((x) => x.is_default) ?? stages[0];
    setStageId(defaultStage?.id ?? "");

    setPriority(
      d.priority === "HIGH" || d.priority === "MEDIUM" || d.priority === "LOW"
        ? d.priority
        : "MEDIUM",
    );
    setFeasibility(
      d.feasibility === "HIGH" ||
        d.feasibility === "MEDIUM" ||
        d.feasibility === "LOW" ||
        d.feasibility === "UNKNOWN"
        ? d.feasibility
        : "UNKNOWN",
    );
    setVisibility(initialVisibility);
    setAssigneeId("");
    setNextReviewDate("");
    setShares([]);
    setInitialized(true);
  }, [
    session,
    metaLoaded,
    initialized,
    categories,
    stages,
    initialVisibility,
  ]);

  // Apply refreshed session draft after research completes (preserve user edits).
  useEffect(() => {
    if (!initialized || researchRun?.status !== "READY") return;
    if (lastAppliedResearchIdRef.current === researchRun.id) return;

    let cancelled = false;

    void (async () => {
      const refreshed = await refresh();
      if (cancelled || lastAppliedResearchIdRef.current === researchRun.id) return;
      if (!refreshed || refreshed.status !== "READY_FOR_REVIEW") return;

      const serverDraft = refreshed.draft ?? {};
      setDraft((prev) => {
        const merged: AiDraft = { ...serverDraft };
        for (const key of editedKeys) {
          if (key === "tags") continue;
          const k = key as keyof AiDraft;
          if (prev && prev[k] !== undefined) {
            (merged as Record<string, unknown>)[k] = prev[k];
          }
        }
        return merged;
      });
      lastAppliedResearchIdRef.current = researchRun.id;
    })();

    return () => {
      cancelled = true;
    };
  }, [researchRun?.status, researchRun?.id, initialized, refresh, editedKeys]);

  const activeMembers = useMemo(
    () =>
      members.filter(
        (m) => m.status === "ACTIVE" && m.user_id !== user?.id,
      ),
    [members, user?.id],
  );

  const basicFields: EditableField[] = useMemo(() => {
    const fields: EditableField[] = TEXT_FIELDS.filter((f) => f.section === "basic").map(
      (f) => ({
        key: f.key,
        label: f.label,
        value: draftValue(draft, f.key),
        source: provenanceFor(session?.field_provenance, f.key, editedKeys),
        multiline: f.key !== "title",
      }),
    );
    fields.push({
      key: "tags_text",
      label: "태그",
      value: tagsText,
      source: editedKeys.has("tags")
        ? "user_edited"
        : provenanceFor(session?.field_provenance, "tags", editedKeys),
    });
    return fields;
  }, [draft, tagsText, session?.field_provenance, editedKeys]);

  const contentFields: EditableField[] = useMemo(
    () =>
      TEXT_FIELDS.filter((f) => f.section === "content").map((f) => ({
        key: f.key,
        label: f.label,
        value: draftValue(draft, f.key) || "정보 없음",
        source: provenanceFor(session?.field_provenance, f.key, editedKeys),
        multiline: true,
      })),
    [draft, session?.field_provenance, editedKeys],
  );

  const titleOk = (draft?.title ?? "").trim().length > 0;
  const selectedUsersOk =
    visibility !== "SELECTED_USERS" || shares.length > 0;

  function startEdit(field: EditableField) {
    setEditingKey(field.key);
    const raw =
      field.key === "tags_text"
        ? tagsText
        : draftValue(draft, field.key as keyof AiDraft);
    setEditValue(raw === "정보 없음" ? "" : raw);
  }

  function saveEdit(key: DraftKey, value?: string) {
    const next = value ?? editValue;
    if (key === "tags_text") {
      setTagsText(next);
      setEditedKeys((prev) => new Set(prev).add("tags"));
    } else {
      setDraft((prev) => ({
        ...(prev ?? {}),
        [key]: next,
      }));
      setEditedKeys((prev) => new Set(prev).add(key));
    }
    if (value === undefined) setEditingKey(null);
  }

  function toggleShare(userId: string) {
    setShares((prev) => {
      const exists = prev.find((s) => s.user_id === userId);
      if (exists) return prev.filter((s) => s.user_id !== userId);
      return [...prev, { user_id: userId, permission: "READ" as const }];
    });
  }

  function setSharePermission(userId: string, permission: IdeaSharePermission) {
    setShares((prev) =>
      prev.map((s) => (s.user_id === userId ? { ...s, permission } : s)),
    );
  }

  function handleRegister() {
    if (researchInProgress) {
      toast.warning("웹 조사 완료 후 등록할 수 있습니다.");
      return;
    }
    if (!titleOk) {
      toast.error("아이디어명을 입력해 주세요.");
      return;
    }
    if (visibility === "SELECTED_USERS" && shares.length === 0) {
      toast.error(
        "지정 사용자 공유에는 최소 1명의 공유 대상이 필요합니다. 비공개 또는 작업공간 공유를 선택해 주세요.",
      );
      return;
    }
    setConfirmError(null);
    setShowConfirmModal(true);
  }

  async function confirmRegister() {
    if (!workspaceId || !sessionId || isConfirming || !titleOk) return;
    setIsConfirming(true);
    setConfirmError(null);
    try {
      const tags = tagsText
        .split(",")
        .map((t) => t.trim())
        .filter(Boolean);

      const payload: AiSessionConfirmRequest = {
        title: (draft?.title ?? "").trim(),
        one_line_definition: emptyToNull(draft?.one_line_definition),
        background: emptyToNull(draft?.background),
        problem: emptyToNull(draft?.problem),
        core_concept: emptyToNull(draft?.core_concept),
        major_features: emptyToNull(draft?.major_features),
        expected_effect: emptyToNull(draft?.expected_effect),
        target_users: emptyToNull(draft?.target_users),
        scenarios: emptyToNull(draft?.scenarios),
        challenges: emptyToNull(draft?.challenges),
        minimum_validation: emptyToNull(draft?.minimum_validation),
        related_project: emptyToNull(draft?.related_project),
        category_id: categoryId || null,
        stage_id: stageId || null,
        priority,
        feasibility,
        visibility,
        assignee_id: assigneeId || null,
        next_review_date: nextReviewDate || null,
        tags,
        shares: visibility === "SELECTED_USERS" ? shares : null,
      };

      const result = await confirmAiSession(workspaceId, sessionId, payload);
      setShowConfirmModal(false);
      toast.success(
        "아이디어가 등록되었습니다",
        `${result.idea.idea_code} · ${result.idea.title}`,
      );
      navigate(`/w/${workspaceId}/ideas/${result.idea.id}`);
    } catch (err) {
      if (err instanceof ApiError && err.status === 409) {
        setConfirmError(
          apiErrorMessage(
            err,
            "이 AI 작업을 등록할 수 없는 상태입니다. 세션을 다시 확인해 주세요.",
          ),
        );
        await refresh();
      } else if (err instanceof ApiError && err.status === 422) {
        setConfirmError(apiErrorMessage(err, "입력값을 확인해 주세요."));
      } else {
        setConfirmError(apiErrorMessage(err, "아이디어 등록에 실패했습니다."));
      }
    } finally {
      setIsConfirming(false);
    }
  }

  function openResearchPanel() {
    const defaults =
      researchQueries.length > 0
        ? researchQueries
        : (session?.research_topics ?? []).slice(0, 5);
    setResearchQueries(defaults.length > 0 ? defaults : [""]);
    setPreviewRun(
      researchRun?.status === "AWAITING_APPROVAL" ? researchRun : null,
    );
    setResearchError(null);
    setResearchPanelOpen(true);
  }

  async function handleResearchPreview() {
    if (!workspaceId || !sessionId || loadingPreview) return;
    const queries = researchQueries.map((q) => q.trim()).filter(Boolean);
    if (queries.length === 0) return;

    setLoadingPreview(true);
    setResearchError(null);
    try {
      const run = await previewWebResearch(workspaceId, sessionId, {
        queries,
        current_draft: draft ?? {},
        user_edited_fields: Array.from(editedKeys).filter((k) => k !== "tags"),
      });
      setPreviewRun(run);
      await refreshResearch();
    } catch (err) {
      setResearchError(apiErrorMessage(err, "검색어 미리보기에 실패했습니다."));
    } finally {
      setLoadingPreview(false);
    }
  }

  async function handleResearchApprove() {
    if (!workspaceId || !sessionId || !previewRun || approvingResearch) return;
    setApprovingResearch(true);
    setResearchError(null);
    try {
      await approveWebResearch(workspaceId, sessionId, previewRun.id);
      setResearchPanelOpen(false);
      setPreviewRun(null);
      await refreshResearch();
      toast.info("웹 검색을 시작합니다", "검색 결과로 초안을 보완합니다.");
    } catch (err) {
      setResearchError(apiErrorMessage(err, "검색 승인에 실패했습니다."));
    } finally {
      setApprovingResearch(false);
    }
  }

  async function handleResearchCancel() {
    if (previewRun?.status === "AWAITING_APPROVAL" && workspaceId && sessionId) {
      try {
        await cancelWebResearch(workspaceId, sessionId, previewRun.id);
      } catch {
        // ignore cancel errors on close
      }
    }
    setResearchPanelOpen(false);
    setPreviewRun(null);
    setResearchError(null);
  }

  async function handleEditResearchQueries() {
    if (!previewRun || !workspaceId || !sessionId) return;
    setResearchError(null);
    try {
      await cancelWebResearch(workspaceId, sessionId, previewRun.id);
      setPreviewRun(null);
      await refreshResearch();
    } catch (err) {
      setResearchError(apiErrorMessage(err, "검색어 수정을 위해 기존 미리보기를 취소하지 못했습니다."));
      throw err;
    }
  }

  async function handleResearchRetry() {
    if (!workspaceId || !sessionId || !researchRun) return;
    try {
      await retryWebResearchRun(workspaceId, sessionId, researchRun.id);
      await refreshResearch();
      toast.info("웹 검색을 다시 시도합니다");
    } catch (err) {
      toast.error(apiErrorMessage(err, "재시도에 실패했습니다."));
    }
  }

  function researchStatusLabel(status: string | undefined): string {
    switch (status) {
      case "QUEUED":
        return "검색 준비 중";
      case "SEARCHING":
        return "웹 자료 검색 중";
      case "REFINING":
        return "검색 근거로 초안 보완 중";
      case "READY":
        return "검색 완료";
      case "FAILED":
        return "검색/보완 실패";
      default:
        return "";
    }
  }

  if (loading || (session?.status === "READY_FOR_REVIEW" && !initialized)) {
    return (
      <div className="min-h-full flex items-center justify-center px-4 py-12">
        <div className="flex items-center gap-2 text-sm text-[#6b6b80]">
          <Loader2 className="w-4 h-4 animate-spin" />
          AI 초안을 불러오는 중...
        </div>
      </div>
    );
  }

  if (error || !session) {
    return (
      <div className="min-h-full flex items-center justify-center px-4 py-12">
        <div className="w-full max-w-lg space-y-4">
          <InlineAlert type="warning" title="AI 초안을 불러올 수 없습니다">
            {error ?? "존재하지 않거나 접근할 수 없는 AI 작업입니다."}
          </InlineAlert>
          <div className="flex gap-2">
            <Button variant="secondary" onClick={() => void refresh()}>
              다시 확인
            </Button>
            <Button
              variant="primary"
              onClick={() => navigate(`/w/${workspaceId}/ideas/new/ai`)}
            >
              새 AI 작업 시작
            </Button>
          </div>
        </div>
      </div>
    );
  }

  if (session.status === "CANCELLED") {
    return (
      <div className="min-h-full flex items-center justify-center px-4 py-12">
        <div className="w-full max-w-lg space-y-4">
          <InlineAlert type="warning" title="취소된 AI 작업">
            이 AI 작업은 취소되었습니다.
          </InlineAlert>
          <Button
            variant="primary"
            onClick={() => navigate(`/w/${workspaceId}/ideas/new/ai`)}
          >
            새 Session 시작
          </Button>
        </div>
      </div>
    );
  }

  if (session.status !== "READY_FOR_REVIEW") {
    return (
      <div className="min-h-full flex items-center justify-center px-4 py-12">
        <div className="flex items-center gap-2 text-sm text-[#6b6b80]">
          <Loader2 className="w-4 h-4 animate-spin" />
          적절한 화면으로 이동 중...
        </div>
      </div>
    );
  }

  const clarificationAnswers = session.clarification_answers ?? [];
  const provenanceEntries = Object.entries(session.field_provenance ?? {});

  return (
    <div className="flex flex-col h-full">
      <div className="px-4 sm:px-8 py-4 bg-white border-b border-[rgba(0,0,0,0.06)]">
        <div className="flex items-center justify-between mb-3">
          <ProgressStepper
            steps={["아이디어 입력", "AI 분석", "초안 검토", "등록 완료"]}
            current={2}
          />
        </div>
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-lg font-bold text-[#111118]">AI 등록 초안 검토</h1>
            <p className="text-sm text-[#6b6b80]">
              AI가 정리한 내용을 확인하고 필요한 경우 수정하세요.
            </p>
          </div>
        </div>
      </div>

      <div className="flex flex-1 overflow-hidden">
        <div className="w-64 border-r border-[rgba(0,0,0,0.06)] bg-[#fafafa] flex flex-col overflow-hidden shrink-0 hidden lg:flex">
          <div className="flex items-center justify-between px-4 py-3 border-b border-[rgba(0,0,0,0.06)]">
            <p className="text-xs font-semibold text-[#6b6b80] uppercase tracking-wider">
              사용자 원문
            </p>
            <button type="button" onClick={() => setOriginalOpen(!originalOpen)}>
              {originalOpen ? (
                <ChevronUp className="w-4 h-4 text-[#9ca3af]" />
              ) : (
                <ChevronDown className="w-4 h-4 text-[#9ca3af]" />
              )}
            </button>
          </div>
          {originalOpen && (
            <div className="flex-1 overflow-y-auto p-4">
              <p className="text-xs text-[#6b6b80] leading-relaxed whitespace-pre-wrap">
                {session.input_text}
              </p>
              {clarificationAnswers.length > 0 && (
                <div className="mt-4 border-t border-[rgba(0,0,0,0.06)] pt-4">
                  <p className="text-xs font-medium text-[#6b6b80] mb-2">
                    추가 질문 답변
                  </p>
                  <ul className="space-y-2">
                    {clarificationAnswers.map((a) => (
                      <li key={a.question_id} className="text-xs text-[#9ca3af]">
                        <span className="font-mono text-[10px] text-[#d1d5db]">
                          {a.question_id}
                        </span>
                        <br />
                        {a.answer}
                      </li>
                    ))}
                  </ul>
                </div>
              )}
            </div>
          )}
        </div>

        <div className="flex-1 overflow-y-auto px-6 py-5">
          <FieldSection
            title="기본정보"
            fields={basicFields}
            editingKey={editingKey}
            editValue={editValue}
            onEdit={startEdit}
            onSave={saveEdit}
            onEditChange={setEditValue}
            onCancelEdit={() => setEditingKey(null)}
            alwaysEdit={directEditMode}
          />
          <FieldSection
            title="아이디어 내용"
            fields={contentFields}
            editingKey={editingKey}
            editValue={editValue}
            onEdit={startEdit}
            onSave={saveEdit}
            onEditChange={setEditValue}
            onCancelEdit={() => setEditingKey(null)}
            alwaysEdit={directEditMode}
          />

          <div className="mb-6">
            <h3 className="text-xs font-semibold text-[#6b6b80] uppercase tracking-wider mb-3">
              관리정보
            </h3>
            <div className="bg-white rounded-xl border border-[rgba(0,0,0,0.07)] p-4 space-y-4">
              <Select
                label="분야 (카테고리)"
                value={categoryId}
                onChange={(e) => setCategoryId(e.target.value)}
                options={[
                  { value: "", label: "선택 안 함" },
                  ...categories.map((c) => ({ value: c.id, label: c.name })),
                ]}
              />
              <Select
                label="단계"
                value={stageId}
                onChange={(e) => setStageId(e.target.value)}
                options={stages.map((s) => ({ value: s.id, label: s.label }))}
              />
              <Select
                label="우선순위"
                value={priority}
                onChange={(e) => setPriority(e.target.value as IdeaPriority)}
                options={[
                  { value: "HIGH", label: "높음" },
                  { value: "MEDIUM", label: "중간" },
                  { value: "LOW", label: "낮음" },
                ]}
              />
              <Select
                label="구현 가능성"
                value={feasibility}
                onChange={(e) =>
                  setFeasibility(e.target.value as IdeaFeasibility)
                }
                options={[
                  { value: "HIGH", label: "높음" },
                  { value: "MEDIUM", label: "중간" },
                  { value: "LOW", label: "낮음" },
                  { value: "UNKNOWN", label: "미평가" },
                ]}
              />
              <Select
                label="공개 범위"
                value={visibility}
                onChange={(e) =>
                  setVisibility(e.target.value as IdeaVisibility)
                }
                options={[
                  { value: "PRIVATE", label: "비공개" },
                  { value: "WORKSPACE", label: "작업공간 공유" },
                  { value: "SELECTED_USERS", label: "지정 사용자 공유" },
                ]}
              />
              {visibility === "SELECTED_USERS" && (
                <div className="rounded-lg border border-[rgba(0,0,0,0.08)] p-3 space-y-2">
                  <p className="text-xs font-medium text-[#6b6b80]">공유 대상</p>
                  {activeMembers.length === 0 ? (
                    <p className="text-xs text-[#9ca3af]">
                      공유할 수 있는 활성 멤버가 없습니다. 비공개 또는 작업공간
                      공유를 선택해 주세요.
                    </p>
                  ) : (
                    activeMembers.map((m) => {
                      const selected = shares.find((s) => s.user_id === m.user_id);
                      return (
                        <div
                          key={m.user_id}
                          className="flex items-center gap-2 text-sm"
                        >
                          <input
                            type="checkbox"
                            checked={!!selected}
                            onChange={() => toggleShare(m.user_id)}
                            className="w-4 h-4 accent-[#4f46e5]"
                          />
                          <span className="flex-1 text-[#111118]">{m.name}</span>
                          {selected && (
                            <select
                              value={selected.permission}
                              onChange={(e) =>
                                setSharePermission(
                                  m.user_id,
                                  e.target.value as IdeaSharePermission,
                                )
                              }
                              className="text-xs border rounded px-2 py-1"
                            >
                              <option value="READ">읽기</option>
                              <option value="EDIT">편집</option>
                            </select>
                          )}
                        </div>
                      );
                    })
                  )}
                </div>
              )}
              <Select
                label="담당자"
                value={assigneeId}
                onChange={(e) => setAssigneeId(e.target.value)}
                options={[
                  { value: "", label: "담당자 없음" },
                  ...members
                    .filter((m) => m.status === "ACTIVE")
                    .map((m) => ({ value: m.user_id, label: m.name })),
                ]}
              />
              <label className="block">
                <span className="text-xs font-medium text-[#6b6b80] mb-1 block">
                  다음 검토일
                </span>
                <input
                  type="date"
                  value={nextReviewDate}
                  onChange={(e) => setNextReviewDate(e.target.value)}
                  className="w-full h-9 rounded-lg border border-[rgba(0,0,0,0.1)] px-3 text-sm"
                />
              </label>
            </div>
          </div>

          <div className="mt-6 bg-[#f8f8fb] rounded-xl border border-[rgba(0,0,0,0.07)] p-4">
            <p className="text-sm font-semibold text-[#6b6b80] mb-1">
              유사 아이디어 검색
            </p>
            <p className="text-xs text-[#9ca3af]">
              유사 아이디어 검색은 추후 제공됩니다.
            </p>
          </div>
        </div>

        {showEvidence && (
          <div className="w-72 border-l border-[rgba(0,0,0,0.06)] flex flex-col overflow-hidden shrink-0 hidden xl:flex">
            <div className="flex items-center justify-between px-4 py-3 border-b border-[rgba(0,0,0,0.06)]">
              <p className="text-xs font-semibold text-[#6b6b80] uppercase tracking-wider">
                근거·출처
              </p>
              <button type="button" onClick={() => setShowEvidence(false)}>
                <X className="w-4 h-4 text-[#9ca3af]" />
              </button>
            </div>
            <div className="flex-1 overflow-y-auto p-4 space-y-3">
              {researchRun?.research_summary && (
                <div className="bg-[#eff6ff] rounded-lg border border-[#bfdbfe] p-3">
                  <p className="text-xs font-semibold text-[#1d4ed8] mb-1">조사 요약 (AI)</p>
                  <p className="text-xs text-[#1e40af] leading-relaxed">
                    {researchRun.research_summary}
                  </p>
                </div>
              )}

              {researchInProgress && (
                <div className="bg-[#fffbeb] rounded-lg border border-[#fde68a] p-3 flex items-center gap-2">
                  <Loader2 className="w-4 h-4 animate-spin text-[#d97706]" />
                  <p className="text-xs text-[#92400e]">
                    {researchStatusLabel(researchRun?.status)}
                  </p>
                </div>
              )}

              {researchPollError && researchInProgress && (
                <p className="text-xs text-[#b45309]">{researchPollError}</p>
              )}

              {researchRun?.status === "FAILED" && (
                <div className="bg-[#fef2f2] rounded-lg border border-[#fecaca] p-3">
                  <p className="text-xs font-semibold text-[#b91c1c] mb-1">웹 조사 실패</p>
                  <p className="text-xs text-[#7f1d1d] mb-2">
                    {researchRun.failure?.message ?? "검색 또는 보완 중 오류가 발생했습니다."}
                  </p>
                  <Button variant="secondary" size="sm" onClick={() => void handleResearchRetry()}>
                    다시 시도
                  </Button>
                </div>
              )}

              {(researchRun?.evidence ?? []).length > 0 ? (
                <div className="space-y-2">
                  {researchRun!.evidence.map((ev) => (
                    <div
                      key={ev.id}
                      className="bg-white rounded-lg border border-[rgba(0,0,0,0.07)] p-3"
                    >
                      <a
                        href={ev.url}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="text-xs font-semibold text-[#2563eb] hover:underline line-clamp-2"
                      >
                        {ev.title}
                      </a>
                      <p className="text-xs text-[#9ca3af] mt-1">
                        {[ev.source_name, ev.domain].filter(Boolean).join(" · ")}
                        {ev.published_at
                          ? ` · ${new Date(ev.published_at).toLocaleDateString("ko")}`
                          : ""}
                      </p>
                      {ev.snippet && (
                        <p className="text-xs text-[#6b6b80] mt-2 leading-relaxed whitespace-pre-wrap">
                          {ev.snippet}
                        </p>
                      )}
                      {ev.related_fields.length > 0 && (
                        <p className="text-xs text-[#9ca3af] mt-2">
                          관련 필드: {ev.related_fields.join(", ")}
                        </p>
                      )}
                    </div>
                  ))}
                </div>
              ) : researchRun?.status === "READY" && (researchRun.result_count ?? 0) === 0 ? (
                <div className="bg-white rounded-lg border border-[rgba(0,0,0,0.07)] p-3">
                  <p className="text-xs font-semibold text-[#111118] mb-1">
                    검색 결과를 찾지 못했습니다.
                  </p>
                  <p className="text-xs text-[#6b6b80]">
                    검색어를 수정하여 다시 시도할 수 있습니다.
                  </p>
                </div>
              ) : (
                <div className="bg-white rounded-lg border border-[rgba(0,0,0,0.07)] p-3">
                  <p className="text-xs font-semibold text-[#111118] mb-1">
                    외부 검색 근거 없음
                  </p>
                  <p className="text-xs text-[#6b6b80]">
                    현재 초안은 사용자 입력과 AI 구조화 결과로 작성되었습니다.
                  </p>
                </div>
              )}

              <div className="bg-[#eff6ff] rounded-lg border border-[#bfdbfe] p-3">
                <p className="text-xs font-semibold text-[#1d4ed8] mb-1">웹 검색으로 보완</p>
                {!allowWebSearch ? (
                  <p className="text-xs text-[#6b6b80]">
                    웹 검색이 현재 시스템 또는 작업공간 정책으로 비활성화되어 있습니다.
                  </p>
                ) : (
                  <>
                    {session.research_recommended && (
                      <p className="text-xs text-[#6b6b80] mb-2">
                        AI가 외부 조사를 권장합니다.
                      </p>
                    )}
                    {(session.research_topics ?? []).length > 0 && !researchRun && (
                      <ul className="list-disc pl-4 space-y-1 mb-2">
                        {(session.research_topics ?? []).map((t) => (
                          <li key={t} className="text-xs text-[#1e40af]">
                            {t}
                          </li>
                        ))}
                      </ul>
                    )}
                    <Button
                      variant="secondary"
                      size="sm"
                      className="mt-1 w-full"
                      disabled={researchInProgress || !allowWebSearch}
                      onClick={openResearchPanel}
                    >
                      웹 검색으로 보완
                    </Button>
                  </>
                )}
              </div>

              {provenanceEntries.length > 0 && (
                <div className="space-y-2">
                  <p className="text-xs font-medium text-[#6b6b80]">필드 출처 요약</p>
                  {provenanceEntries.map(([field, p]) => {
                    const badge = mapProvenanceSource(
                      p.final_source ?? p.source ?? p.original_source,
                    );
                    if (!badge) return null;
                    return (
                      <div
                        key={field}
                        className="flex items-center justify-between gap-2 text-xs"
                      >
                        <span className="text-[#9ca3af] truncate">{field}</span>
                        <SourceBadge type={badge} />
                      </div>
                    );
                  })}
                </div>
              )}
            </div>
          </div>
        )}
      </div>

      <div className="px-4 sm:px-8 py-4 bg-white border-t border-[rgba(0,0,0,0.06)] flex flex-wrap items-center gap-2 sm:gap-3">
        <Button
          variant="ghost"
          icon={<ArrowLeft className="w-4 h-4" />}
          onClick={() =>
            navigate(
              `/w/${workspaceId}/ideas/new/ai/analyzing/${sessionId}?visibility=${visibility}`,
            )
          }
        >
          이전
        </Button>
        <Button variant="secondary" disabled title="추후 제공">
          임시 저장
        </Button>
        <div className="ml-auto flex items-center gap-2 flex-wrap">
          <Button
            variant="ghost"
            icon={<RefreshCw className="w-3.5 h-3.5" />}
            disabled
            title="추후 제공"
          >
            전체 다시 생성
          </Button>
          <Button
            variant="secondary"
            icon={<Pencil className="w-3.5 h-3.5" />}
            onClick={() => setDirectEditMode((v) => !v)}
          >
            {directEditMode ? "수정 모드 끄기" : "직접 수정 모드"}
          </Button>
          <Button
            variant="primary"
            icon={<Check className="w-4 h-4" />}
            onClick={handleRegister}
            disabled={!titleOk || !selectedUsersOk || researchInProgress}
            title={researchInProgress ? "웹 조사 완료 후 등록할 수 있습니다." : undefined}
          >
            아이디어 등록
          </Button>
        </div>
      </div>

      {showConfirmModal && (
        <div className="fixed inset-0 bg-black/30 z-50 flex items-center justify-center p-4">
          <div className="bg-white rounded-2xl border border-[rgba(0,0,0,0.08)] shadow-xl w-full max-w-sm p-6">
            <div className="flex items-center gap-2 mb-3">
              <Sparkles className="w-5 h-5 text-[#4f46e5]" />
              <h3 className="text-base font-bold text-[#111118]">
                아이디어를 등록하시겠습니까?
              </h3>
            </div>
            <p className="text-sm text-[#6b6b80] mb-3">
              검토된 내용으로 아이디어가 등록됩니다. 등록 후에도 편집이 가능합니다.
            </p>
            {confirmError && (
              <div className="mb-3">
                <InlineAlert type="error" title="등록 실패">
                  {confirmError}
                </InlineAlert>
              </div>
            )}
            <div className="flex gap-2">
              <Button
                variant="ghost"
                className="flex-1"
                disabled={isConfirming}
                onClick={() => setShowConfirmModal(false)}
              >
                취소
              </Button>
              <Button
                variant="primary"
                className="flex-1"
                loading={isConfirming}
                onClick={() => void confirmRegister()}
              >
                등록
              </Button>
            </div>
          </div>
        </div>
      )}

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
      />
    </div>
  );
}

function emptyToNull(value: string | null | undefined): string | null {
  if (value == null) return null;
  const t = value.trim();
  return t.length ? t : null;
}

function FieldSection({
  title,
  fields,
  editingKey,
  editValue,
  onEdit,
  onSave,
  onEditChange,
  onCancelEdit,
  alwaysEdit,
}: {
  title: string;
  fields: EditableField[];
  editingKey: DraftKey | null;
  editValue: string;
  onEdit: (f: EditableField) => void;
  onSave: (key: DraftKey, value?: string) => void;
  onEditChange: (v: string) => void;
  onCancelEdit: () => void;
  alwaysEdit: boolean;
}) {
  return (
    <div className="mb-6">
      <h3 className="text-xs font-semibold text-[#6b6b80] uppercase tracking-wider mb-3">
        {title}
      </h3>
      <div className="bg-white rounded-xl border border-[rgba(0,0,0,0.07)] divide-y divide-[rgba(0,0,0,0.05)]">
        {fields.map((field) => {
          const isEditing = alwaysEdit || editingKey === field.key;
          const displayValue =
            field.value === "정보 없음" ? "" : field.value;
          return (
            <div key={field.key} className="p-4 group">
              <div className="flex items-center gap-2 mb-1.5">
                <span className="text-xs font-semibold text-[#6b6b80]">
                  {field.label}
                </span>
                {field.source && <SourceBadge type={field.source} />}
                {!alwaysEdit && (
                  <div className="ml-auto flex items-center gap-1 opacity-0 group-hover:opacity-100 transition-opacity">
                    <button
                      type="button"
                      onClick={() => onEdit(field)}
                      className="p-1 rounded hover:bg-[#f0f0f5] text-[#6b6b80]"
                    >
                      <Pencil className="w-3 h-3" />
                    </button>
                  </div>
                )}
              </div>
              {isEditing ? (
                <div>
                  <textarea
                    value={alwaysEdit ? displayValue : editValue}
                    onChange={(e) => {
                      if (alwaysEdit) {
                        onSave(field.key, e.target.value);
                      } else {
                        onEditChange(e.target.value);
                      }
                    }}
                    className={clsx(
                      "w-full rounded-lg border border-[#4f46e5] bg-white px-3 py-2 text-sm text-[#111118] resize-none focus:outline-none focus:ring-2 focus:ring-[#4f46e5]/20",
                      field.multiline ? "min-h-[60px]" : "min-h-[40px]",
                    )}
                    autoFocus={!alwaysEdit}
                  />
                  {!alwaysEdit && editingKey === field.key && (
                    <div className="flex gap-2 mt-2">
                      <Button
                        variant="primary"
                        size="sm"
                        onClick={() => onSave(field.key)}
                      >
                        저장
                      </Button>
                      <Button variant="ghost" size="sm" onClick={onCancelEdit}>
                        취소
                      </Button>
                    </div>
                  )}
                </div>
              ) : (
                <p className="text-sm text-[#111118] leading-relaxed whitespace-pre-wrap">
                  {field.value || "정보 없음"}
                </p>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}
