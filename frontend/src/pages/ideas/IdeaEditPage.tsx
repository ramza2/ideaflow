import { useEffect, useMemo, useState } from "react";
import { useNavigate, useParams } from "react-router";
import { Save, Eye, X } from "lucide-react";
import { createIdea, getIdea, updateIdea } from "../../api/ideas";
import { listCategories, listMembers, listStages } from "../../api/workspaces";
import { apiErrorMessage } from "../../api/client";
import { Button } from "../../components/common/Button";
import { Input, Select } from "../../components/common/Input";
import { toast } from "../../components/common/Toast";
import { EmptyState } from "../../components/common/EmptyState";
import type {
  CategoryPublic,
  IdeaDetail,
  IdeaFeasibility,
  IdeaPriority,
  IdeaVisibility,
  MemberPublic,
  StagePublic,
} from "../../types/api";

export function IdeaEditPage() {
  const navigate = useNavigate();
  const { workspaceId = "", ideaId } = useParams();
  const isNew = !ideaId;

  const [loading, setLoading] = useState(!isNew);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [existing, setExisting] = useState<IdeaDetail | null>(null);
  const [stages, setStages] = useState<StagePublic[]>([]);
  const [categories, setCategories] = useState<CategoryPublic[]>([]);
  const [members, setMembers] = useState<MemberPublic[]>([]);

  const [title, setTitle] = useState("");
  const [oneLiner, setOneLiner] = useState("");
  const [originalText, setOriginalText] = useState("");
  const [categoryId, setCategoryId] = useState("");
  const [tags, setTags] = useState("");
  const [stageId, setStageId] = useState("");
  const [priority, setPriority] = useState<IdeaPriority>("MEDIUM");
  const [feasibility, setFeasibility] = useState<IdeaFeasibility>("UNKNOWN");
  const [visibility, setVisibility] = useState<IdeaVisibility>("PRIVATE");
  const [assigneeId, setAssigneeId] = useState("");
  const [nextReviewDate, setNextReviewDate] = useState("");
  const [background, setBackground] = useState("");
  const [problem, setProblem] = useState("");
  const [concept, setConcept] = useState("");
  const [features, setFeatures] = useState("");
  const [expectedEffect, setExpectedEffect] = useState("");
  const [targetUsers, setTargetUsers] = useState("");
  const [scenario, setScenario] = useState("");
  const [challenges, setChallenges] = useState("");
  const [validationMethod, setValidationMethod] = useState("");
  const [relatedProject, setRelatedProject] = useState("");

  const access = existing?.current_user_access;
  const isOwner = !existing || access === "OWNER";
  const isEditShare = access === "EDIT";
  const canEditOriginal = isOwner;
  const canEditVisibility = isOwner;

  useEffect(() => {
    if (!workspaceId) return;
    void Promise.all([
      listStages(workspaceId),
      listCategories(workspaceId),
      listMembers(workspaceId),
    ]).then(([s, c, m]) => {
      setStages(s);
      setCategories(c);
      setMembers(m);
      if (isNew) {
        const defaultStage = s.find((x) => x.is_default) ?? s[0];
        if (defaultStage) setStageId(defaultStage.id);
      }
    }).catch(() => {
      toast.error("양식 데이터를 불러오지 못했습니다.");
    });
  }, [workspaceId, isNew]);

  useEffect(() => {
    if (isNew || !workspaceId || !ideaId) return;
    let cancelled = false;
    setLoading(true);
    void getIdea(workspaceId, ideaId)
      .then((idea) => {
        if (cancelled) return;
        setExisting(idea);
        setTitle(idea.title);
        setOneLiner(idea.one_line_definition ?? "");
        setOriginalText(idea.original_text ?? "");
        setCategoryId(idea.category?.id ?? "");
        setTags(idea.tags.map((t) => t.name).join(", "));
        setStageId(idea.stage.id);
        setPriority(idea.priority);
        setFeasibility(idea.feasibility);
        setVisibility(idea.visibility);
        setAssigneeId(idea.assignee?.id ?? "");
        setNextReviewDate(idea.next_review_date ?? "");
        setBackground(idea.background ?? "");
        setProblem(idea.problem ?? "");
        setConcept(idea.core_concept ?? "");
        setFeatures(idea.major_features ?? "");
        setExpectedEffect(idea.expected_effect ?? "");
        setTargetUsers(idea.target_users ?? "");
        setScenario(idea.scenarios ?? "");
        setChallenges(idea.challenges ?? "");
        setValidationMethod(idea.minimum_validation ?? "");
        setRelatedProject(idea.related_project ?? "");
      })
      .catch((err) => {
        if (!cancelled) setError(apiErrorMessage(err));
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [isNew, workspaceId, ideaId]);

  const activeMembers = useMemo(
    () => members.filter((m) => m.status === "ACTIVE"),
    [members],
  );

  async function handleSave() {
    if (!workspaceId || !title.trim()) {
      toast.error("아이디어명을 입력해 주세요.");
      return;
    }
    if (!stageId) {
      toast.error("단계를 선택해 주세요.");
      return;
    }

    setSubmitting(true);
    try {
      const tagList = tags
        .split(",")
        .map((t) => t.trim())
        .filter(Boolean);

      if (isNew) {
        const created = await createIdea(workspaceId, {
          title: title.trim(),
          one_line_definition: oneLiner.trim() || null,
          original_text: originalText.trim() || null,
          background: background.trim() || null,
          problem: problem.trim() || null,
          core_concept: concept.trim() || null,
          major_features: features.trim() || null,
          expected_effect: expectedEffect.trim() || null,
          target_users: targetUsers.trim() || null,
          scenarios: scenario.trim() || null,
          challenges: challenges.trim() || null,
          minimum_validation: validationMethod.trim() || null,
          related_project: relatedProject.trim() || null,
          category_id: categoryId || null,
          stage_id: stageId,
          priority,
          feasibility,
          visibility,
          assignee_id: assigneeId || null,
          next_review_date: nextReviewDate || null,
          tags: tagList,
        });
        toast.success("아이디어가 등록되었습니다.");
        navigate(`/w/${workspaceId}/ideas/${created.id}`, { replace: true });
        return;
      }

      if (!ideaId || !existing) return;

      const payload: Record<string, unknown> = {};
      if (title.trim() !== existing.title) payload.title = title.trim();
      const ol = oneLiner.trim() || null;
      if (ol !== (existing.one_line_definition ?? null)) payload.one_line_definition = ol;
      if (canEditOriginal) {
        const ot = originalText.trim() || null;
        if (ot !== (existing.original_text ?? null)) payload.original_text = ot;
      }
      if (stageId !== existing.stage.id) payload.stage_id = stageId;
      if (priority !== existing.priority) payload.priority = priority;
      if (feasibility !== existing.feasibility) payload.feasibility = feasibility;
      if (canEditVisibility && visibility !== existing.visibility) payload.visibility = visibility;

      const cat = categoryId || null;
      if (cat !== (existing.category?.id ?? null)) payload.category_id = cat;

      const assignee = assigneeId || null;
      if (assignee !== (existing.assignee?.id ?? null)) payload.assignee_id = assignee;

      const nrd = nextReviewDate || null;
      if (nrd !== (existing.next_review_date ?? null)) payload.next_review_date = nrd;

      const narrativeFields: [string, string | null, string | null][] = [
        ["background", background.trim() || null, existing.background ?? null],
        ["problem", problem.trim() || null, existing.problem ?? null],
        ["core_concept", concept.trim() || null, existing.core_concept ?? null],
        ["major_features", features.trim() || null, existing.major_features ?? null],
        ["expected_effect", expectedEffect.trim() || null, existing.expected_effect ?? null],
        ["target_users", targetUsers.trim() || null, existing.target_users ?? null],
        ["scenarios", scenario.trim() || null, existing.scenarios ?? null],
        ["challenges", challenges.trim() || null, existing.challenges ?? null],
        ["minimum_validation", validationMethod.trim() || null, existing.minimum_validation ?? null],
        ["related_project", relatedProject.trim() || null, existing.related_project ?? null],
      ];
      for (const [key, val, prev] of narrativeFields) {
        if (val !== prev) payload[key] = val;
      }

      const prevTags = existing.tags.map((t) => t.name).sort().join(",");
      const nextTags = tagList.sort().join(",");
      if (prevTags !== nextTags) payload.tags = tagList;

      const updated = await updateIdea(workspaceId, ideaId, payload);
      toast.success("아이디어가 수정되었습니다.");
      navigate(`/w/${workspaceId}/ideas/${updated.id}`, { replace: true });
    } catch (err) {
      toast.error(apiErrorMessage(err, "저장에 실패했습니다."));
    } finally {
      setSubmitting(false);
    }
  }

  if (loading) {
    return <div className="p-8 text-sm text-[#6b6b80]">불러오는 중...</div>;
  }

  if (error) {
    return (
      <div className="p-8">
        <EmptyState title="아이디어를 불러올 수 없습니다" description={error} />
      </div>
    );
  }

  if (!isNew && existing && access === "READ") {
    return (
      <div className="p-8">
        <EmptyState
          title="편집 권한이 없습니다"
          description="이 아이디어는 읽기 전용입니다."
          action={
            <Button variant="secondary" size="sm" onClick={() => navigate(`/w/${workspaceId}/ideas/${ideaId}`)}>
              상세로 돌아가기
            </Button>
          }
        />
      </div>
    );
  }

  function FieldWrapper({ label, value, onChange, disabled = false }: { label: string; value: string; onChange: (v: string) => void; disabled?: boolean }) {
    return (
      <div className="flex flex-col gap-1.5">
        <label className="text-sm font-medium text-[#111118]">{label}</label>
        <textarea
          value={value}
          onChange={(e) => onChange(e.target.value)}
          disabled={disabled}
          className="w-full rounded-lg border border-[rgba(0,0,0,0.1)] bg-white px-3 py-2.5 text-sm text-[#111118] placeholder:text-[#9ca3af] resize-none focus:outline-none focus:ring-2 focus:ring-[#4f46e5]/20 focus:border-[#4f46e5] transition-colors h-24 disabled:bg-[#f4f4f8] disabled:text-[#9ca3af]"
        />
      </div>
    );
  }

  return (
    <div className="flex flex-col h-full">
      <div className="px-8 py-4 bg-white border-b border-[rgba(0,0,0,0.06)] flex items-center justify-between">
        <h1 className="text-lg font-bold text-[#111118]">
          {isNew ? "새 아이디어 직접 등록" : "아이디어 편집"}
        </h1>
        <button type="button" onClick={() => navigate(-1)} className="w-8 h-8 flex items-center justify-center rounded-lg text-[#6b6b80] hover:bg-[#f4f4f8]">
          <X className="w-4 h-4" />
        </button>
      </div>

      <div className="flex-1 overflow-y-auto">
        <div className="grid grid-cols-1 lg:grid-cols-[1fr_300px] gap-0 h-full">
          <div className="px-8 py-6 space-y-5 border-r border-[rgba(0,0,0,0.06)]">
            <div className="grid grid-cols-2 gap-4">
              <Input label="아이디어명" value={title} onChange={(e) => setTitle(e.target.value)} placeholder="짧고 명확하게" required />
              <Input label="한 줄 정의" value={oneLiner} onChange={(e) => setOneLiner(e.target.value)} placeholder="핵심을 한 문장으로" />
            </div>
            {canEditOriginal && (
              <FieldWrapper label="원문" value={originalText} onChange={setOriginalText} disabled={isEditShare} />
            )}
            <div className="grid grid-cols-2 gap-4">
              <Select
                label="분야"
                value={categoryId}
                onChange={(e) => setCategoryId(e.target.value)}
                options={[
                  { value: "", label: "선택 안 함" },
                  ...categories.map((c) => ({ value: c.id, label: c.name })),
                ]}
              />
              <Input label="태그 (쉼표로 구분)" value={tags} onChange={(e) => setTags(e.target.value)} placeholder="AI, 협업" />
            </div>
            <div className="border-t border-[rgba(0,0,0,0.06)] pt-5 space-y-5">
              <FieldWrapper label="배경" value={background} onChange={setBackground} />
              <FieldWrapper label="해결하려는 문제" value={problem} onChange={setProblem} />
              <FieldWrapper label="핵심 개념" value={concept} onChange={setConcept} />
              <FieldWrapper label="주요 기능" value={features} onChange={setFeatures} />
              <FieldWrapper label="기대 효과" value={expectedEffect} onChange={setExpectedEffect} />
              <FieldWrapper label="예상 사용자" value={targetUsers} onChange={setTargetUsers} />
              <FieldWrapper label="사용 시나리오" value={scenario} onChange={setScenario} />
              <FieldWrapper label="주요 난제" value={challenges} onChange={setChallenges} />
              <FieldWrapper label="최소 검증 방법" value={validationMethod} onChange={setValidationMethod} />
              <FieldWrapper label="관련 프로젝트" value={relatedProject} onChange={setRelatedProject} />
            </div>
          </div>

          <div className="px-6 py-6 space-y-4">
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
              onChange={(e) => setFeasibility(e.target.value as IdeaFeasibility)}
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
              onChange={(e) => setVisibility(e.target.value as IdeaVisibility)}
              disabled={!canEditVisibility}
              options={[
                { value: "PRIVATE", label: "비공개" },
                { value: "WORKSPACE", label: "작업공간 공유" },
                { value: "SELECTED_USERS", label: "지정 사용자 공유" },
              ]}
            />
            <Select
              label="담당자"
              value={assigneeId}
              onChange={(e) => setAssigneeId(e.target.value)}
              options={[
                { value: "", label: "담당자 없음" },
                ...activeMembers.map((m) => ({ value: m.user_id, label: m.name })),
              ]}
            />
            <Input label="다음 검토일" type="date" value={nextReviewDate} onChange={(e) => setNextReviewDate(e.target.value)} />
          </div>
        </div>
      </div>

      <div className="px-8 py-4 bg-white border-t border-[rgba(0,0,0,0.06)] flex items-center gap-2">
        <Button variant="ghost" onClick={() => navigate(-1)}>취소</Button>
        <Button variant="ghost" icon={<Eye className="w-3.5 h-3.5" />} disabled>미리보기</Button>
        <div className="ml-auto">
          <Button
            variant="primary"
            icon={<Save className="w-3.5 h-3.5" />}
            onClick={() => void handleSave()}
            loading={submitting}
            disabled={submitting}
          >
            저장
          </Button>
        </div>
      </div>
    </div>
  );
}
