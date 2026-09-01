import { useEffect, useState } from "react";
import { CheckCircle2, FlaskConical, Plus, X } from "lucide-react";
import {
  cancelValidation,
  completeValidation,
  createValidation,
  listValidations,
  markValidationReady,
  startValidation,
  updateValidation,
} from "../../api/validations";
import { apiErrorMessage, ApiError } from "../../api/client";
import { Button } from "../common/Button";
import { Badge } from "../common/Badge";
import { EmptyState } from "../common/EmptyState";
import { toast } from "../common/Toast";
import type {
  IdeaDetail,
  IdeaValidation,
  IdeaValidationOutcome,
  IdeaValidationStatus,
  StageRef,
} from "../../types/api";

const STATUS_LABEL: Record<IdeaValidationStatus, string> = {
  DRAFT: "초안",
  READY: "준비 완료",
  RUNNING: "진행 중",
  COMPLETED: "완료",
  CANCELLED: "취소됨",
};

const STATUS_CLASS: Record<IdeaValidationStatus, string> = {
  DRAFT: "bg-[#f0f0f5] text-[#6b6b80]",
  READY: "bg-[#eff6ff] text-[#2563eb]",
  RUNNING: "bg-[#fffbeb] text-[#d97706]",
  COMPLETED: "bg-[#f0fdf4] text-[#16a34a]",
  CANCELLED: "bg-[#fef2f2] text-[#dc2626]",
};

const OUTCOME_LABEL: Record<IdeaValidationOutcome, string> = {
  PASS: "통과",
  PARTIAL: "부분 통과",
  FAIL: "실패",
  INCONCLUSIVE: "결론 불충분",
};

const VALIDATION_ERROR_MESSAGES: Record<string, string> = {
  IDEA_NOT_READY_FOR_VALIDATION: "아이디어 상태를 먼저 '검증 후보'로 변경해 주세요.",
  INVALID_VALIDATION_TRANSITION: "현재 검증 상태에서는 이 작업을 수행할 수 없습니다.",
  VALIDATION_NOT_EDITABLE: "완료되거나 취소된 검증 계획은 수정할 수 없습니다.",
  VALIDATION_NOT_FOUND: "검증 계획을 찾을 수 없거나 접근 권한이 없습니다.",
};

function validationErrorMessage(err: unknown): string {
  if (err instanceof ApiError && err.code && VALIDATION_ERROR_MESSAGES[err.code]) {
    return VALIDATION_ERROR_MESSAGES[err.code];
  }
  return apiErrorMessage(err);
}

interface FormState {
  title: string;
  hypothesis: string;
  method: string;
  success_criteria: string;
  planned_evidence: string;
  due_date: string;
}

const EMPTY_FORM: FormState = {
  title: "",
  hypothesis: "",
  method: "",
  success_criteria: "",
  planned_evidence: "",
  due_date: "",
};

interface Props {
  workspaceId: string;
  idea: IdeaDetail;
  canEdit: boolean;
  onIdeaStageChange: (stage: StageRef) => void;
}

export function IdeaValidationPanel({
  workspaceId,
  idea,
  canEdit,
  onIdeaStageChange,
}: Props) {
  const [items, setItems] = useState<IdeaValidation[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const [formOpen, setFormOpen] = useState(false);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [form, setForm] = useState<FormState>(EMPTY_FORM);
  const [saving, setSaving] = useState(false);

  const [completeOpen, setCompleteOpen] = useState(false);
  const [completeTargetId, setCompleteTargetId] = useState<string | null>(null);
  const [outcome, setOutcome] = useState<IdeaValidationOutcome>("PASS");
  const [resultSummary, setResultSummary] = useState("");
  const [evidenceSummary, setEvidenceSummary] = useState("");
  const [completing, setCompleting] = useState(false);

  async function reload() {
    setLoading(true);
    setError(null);
    try {
      const data = await listValidations(workspaceId, idea.id);
      setItems(data.items);
    } catch (err) {
      setError(apiErrorMessage(err));
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    void reload();
  }, [workspaceId, idea.id]);

  function openCreate() {
    setEditingId(null);
    setForm({
      ...EMPTY_FORM,
      method: idea.minimum_validation?.trim() || "",
    });
    setFormOpen(true);
  }

  function openEdit(row: IdeaValidation) {
    setEditingId(row.id);
    setForm({
      title: row.title,
      hypothesis: row.hypothesis,
      method: row.method,
      success_criteria: row.success_criteria,
      planned_evidence: row.planned_evidence ?? "",
      due_date: row.due_date ?? "",
    });
    setFormOpen(true);
  }

  async function saveForm() {
    setSaving(true);
    try {
      const payload = {
        title: form.title.trim(),
        hypothesis: form.hypothesis.trim(),
        method: form.method.trim(),
        success_criteria: form.success_criteria.trim(),
        planned_evidence: form.planned_evidence.trim() || null,
        due_date: form.due_date || null,
      };
      if (editingId) {
        await updateValidation(workspaceId, idea.id, editingId, payload);
        toast.success("검증 계획이 수정되었습니다.");
      } else {
        await createValidation(workspaceId, idea.id, payload);
        toast.success("검증 계획이 추가되었습니다.");
      }
      setFormOpen(false);
      await reload();
    } catch (err) {
      toast.error(validationErrorMessage(err));
    } finally {
      setSaving(false);
    }
  }

  async function runAction(
    action: () => Promise<unknown>,
    successMessage: string,
  ) {
    try {
      await action();
      toast.success(successMessage);
      await reload();
    } catch (err) {
      toast.error(validationErrorMessage(err));
    }
  }

  async function handleStart(row: IdeaValidation) {
    try {
      const result = await startValidation(workspaceId, idea.id, row.id);
      onIdeaStageChange(result.idea_stage);
      toast.success("검증을 시작했습니다.");
      await reload();
    } catch (err) {
      toast.error(validationErrorMessage(err));
    }
  }

  async function handleComplete() {
    if (!completeTargetId) return;
    setCompleting(true);
    try {
      await completeValidation(workspaceId, idea.id, completeTargetId, {
        outcome,
        result_summary: resultSummary.trim(),
        evidence_summary: evidenceSummary.trim() || null,
      });
      toast.success("검증이 완료되었습니다.");
      setCompleteOpen(false);
      setCompleteTargetId(null);
      await reload();
    } catch (err) {
      toast.error(validationErrorMessage(err));
    } finally {
      setCompleting(false);
    }
  }

  return (
    <div className="max-w-2xl space-y-4">
      <div className="flex items-center justify-between gap-3">
        <div>
          <h3 className="text-sm font-semibold text-[#111118]">검증 계획</h3>
          <p className="text-xs text-[#6b6b80] mt-0.5">
            가설·방법·성공 기준을 기록하고 수동으로 검증을 진행합니다.
          </p>
        </div>
        {canEdit && (
          <Button size="sm" icon={<Plus className="w-3.5 h-3.5" />} onClick={openCreate}>
            검증 계획 추가
          </Button>
        )}
      </div>

      {loading && <p className="text-sm text-[#6b6b80]">불러오는 중…</p>}
      {error && <p className="text-sm text-[#dc2626]">{error}</p>}

      {!loading && !error && items.length === 0 && (
        <EmptyState
          icon={<FlaskConical className="w-5 h-5" />}
          title="검증 계획이 없습니다"
          description={
            canEdit
              ? "가설과 성공 기준을 정리한 검증 계획을 추가하세요."
              : "등록된 검증 계획이 없습니다."
          }
          action={
            canEdit ? (
              <Button size="sm" icon={<Plus className="w-3.5 h-3.5" />} onClick={openCreate}>
                검증 계획 추가
              </Button>
            ) : undefined
          }
        />
      )}

      <div className="space-y-3">
        {items.map((row) => (
          <div
            key={row.id}
            className="rounded-xl border border-[rgba(0,0,0,0.08)] bg-white p-4 space-y-3"
          >
            <div className="flex items-start justify-between gap-3">
              <div className="min-w-0">
                <div className="flex flex-wrap items-center gap-2 mb-1">
                  <Badge className={STATUS_CLASS[row.status]}>{STATUS_LABEL[row.status]}</Badge>
                  {row.outcome && (
                    <Badge className="bg-[#f5f3ff] text-[#7c3aed]">
                      {OUTCOME_LABEL[row.outcome]}
                    </Badge>
                  )}
                </div>
                <h4 className="text-sm font-semibold text-[#111118]">{row.title}</h4>
                <p className="text-xs text-[#9ca3af] mt-1">
                  {row.created_by.name}
                  {row.due_date ? ` · 목표일 ${row.due_date}` : ""}
                  {row.started_at
                    ? ` · 시작 ${new Date(row.started_at).toLocaleDateString("ko")}`
                    : ""}
                  {row.completed_at
                    ? ` · 완료 ${new Date(row.completed_at).toLocaleDateString("ko")}`
                    : ""}
                </p>
              </div>
            </div>

            <Field label="가설" value={row.hypothesis} />
            <Field label="성공 기준" value={row.success_criteria} />
            <Field label="검증 방법" value={row.method} />
            {row.planned_evidence && <Field label="수집할 근거" value={row.planned_evidence} />}
            {row.result_summary && <Field label="결과 요약" value={row.result_summary} />}
            {row.evidence_summary && <Field label="근거 요약" value={row.evidence_summary} />}

            {canEdit && (
              <div className="flex flex-wrap gap-2 pt-1">
                {(row.status === "DRAFT" || row.status === "READY") && (
                  <Button size="sm" variant="secondary" onClick={() => openEdit(row)}>
                    수정
                  </Button>
                )}
                {row.status === "DRAFT" && (
                  <Button
                    size="sm"
                    variant="secondary"
                    onClick={() =>
                      void runAction(
                        () => markValidationReady(workspaceId, idea.id, row.id),
                        "준비 완료로 표시했습니다.",
                      )
                    }
                  >
                    준비 완료
                  </Button>
                )}
                {row.status === "READY" && (
                  <Button size="sm" onClick={() => void handleStart(row)}>
                    검증 시작
                  </Button>
                )}
                {row.status === "RUNNING" && (
                  <Button
                    size="sm"
                    icon={<CheckCircle2 className="w-3.5 h-3.5" />}
                    onClick={() => {
                      setCompleteTargetId(row.id);
                      setOutcome("PASS");
                      setResultSummary("");
                      setEvidenceSummary("");
                      setCompleteOpen(true);
                    }}
                  >
                    검증 완료
                  </Button>
                )}
                {(row.status === "DRAFT" ||
                  row.status === "READY" ||
                  row.status === "RUNNING") && (
                  <Button
                    size="sm"
                    variant="secondary"
                    onClick={() =>
                      void runAction(
                        () => cancelValidation(workspaceId, idea.id, row.id),
                        "검증이 취소되었습니다.",
                      )
                    }
                  >
                    취소
                  </Button>
                )}
              </div>
            )}
          </div>
        ))}
      </div>

      {formOpen && (
        <Modal title={editingId ? "검증 계획 수정" : "검증 계획 추가"} onClose={() => setFormOpen(false)}>
          <div className="space-y-3">
            <Input label="제목" value={form.title} onChange={(v) => setForm({ ...form, title: v })} />
            <TextArea label="가설" value={form.hypothesis} onChange={(v) => setForm({ ...form, hypothesis: v })} />
            <TextArea label="검증 방법" value={form.method} onChange={(v) => setForm({ ...form, method: v })} />
            <TextArea
              label="성공 기준"
              value={form.success_criteria}
              onChange={(v) => setForm({ ...form, success_criteria: v })}
            />
            <TextArea
              label="수집할 근거"
              value={form.planned_evidence}
              onChange={(v) => setForm({ ...form, planned_evidence: v })}
            />
            <Input
              label="목표일"
              type="date"
              value={form.due_date}
              onChange={(v) => setForm({ ...form, due_date: v })}
            />
            <div className="flex justify-end gap-2 pt-2">
              <Button variant="secondary" size="sm" onClick={() => setFormOpen(false)}>
                닫기
              </Button>
              <Button size="sm" disabled={saving} onClick={() => void saveForm()}>
                저장
              </Button>
            </div>
          </div>
        </Modal>
      )}

      {completeOpen && (
        <Modal title="검증 완료" onClose={() => setCompleteOpen(false)}>
          <div className="space-y-3">
            <label className="block text-xs font-medium text-[#6b6b80]">결과 판정</label>
            <select
              className="w-full rounded-lg border border-[rgba(0,0,0,0.1)] px-3 py-2 text-sm"
              value={outcome}
              onChange={(e) => setOutcome(e.target.value as IdeaValidationOutcome)}
            >
              {(Object.keys(OUTCOME_LABEL) as IdeaValidationOutcome[]).map((key) => (
                <option key={key} value={key}>
                  {OUTCOME_LABEL[key]}
                </option>
              ))}
            </select>
            <TextArea label="결과 요약" value={resultSummary} onChange={setResultSummary} />
            <TextArea label="근거 요약 (선택)" value={evidenceSummary} onChange={setEvidenceSummary} />
            <div className="flex justify-end gap-2 pt-2">
              <Button variant="secondary" size="sm" onClick={() => setCompleteOpen(false)}>
                닫기
              </Button>
              <Button size="sm" disabled={completing} onClick={() => void handleComplete()}>
                완료 저장
              </Button>
            </div>
          </div>
        </Modal>
      )}
    </div>
  );
}

function Field({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <p className="text-[11px] font-semibold uppercase tracking-wider text-[#6b6b80] mb-1">{label}</p>
      <p className="text-sm text-[#111118] whitespace-pre-wrap">{value}</p>
    </div>
  );
}

function Modal({
  title,
  onClose,
  children,
}: {
  title: string;
  onClose: () => void;
  children: React.ReactNode;
}) {
  return (
    <div className="fixed inset-0 z-40 flex items-center justify-center bg-black/30 p-4">
      <div className="w-full max-w-md rounded-2xl bg-white shadow-xl">
        <div className="flex items-center justify-between px-5 py-4 border-b border-[rgba(0,0,0,0.06)]">
          <h3 className="text-sm font-semibold text-[#111118]">{title}</h3>
          <button
            type="button"
            onClick={onClose}
            className="w-7 h-7 flex items-center justify-center rounded-lg text-[#6b6b80] hover:bg-[#f4f4f8]"
          >
            <X className="w-4 h-4" />
          </button>
        </div>
        <div className="p-5">{children}</div>
      </div>
    </div>
  );
}

function Input({
  label,
  value,
  onChange,
  type = "text",
}: {
  label: string;
  value: string;
  onChange: (v: string) => void;
  type?: string;
}) {
  return (
    <label className="block">
      <span className="text-xs font-medium text-[#6b6b80]">{label}</span>
      <input
        type={type}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        className="mt-1 w-full rounded-lg border border-[rgba(0,0,0,0.1)] px-3 py-2 text-sm"
      />
    </label>
  );
}

function TextArea({
  label,
  value,
  onChange,
}: {
  label: string;
  value: string;
  onChange: (v: string) => void;
}) {
  return (
    <label className="block">
      <span className="text-xs font-medium text-[#6b6b80]">{label}</span>
      <textarea
        value={value}
        onChange={(e) => onChange(e.target.value)}
        rows={3}
        className="mt-1 w-full rounded-lg border border-[rgba(0,0,0,0.1)] px-3 py-2 text-sm resize-y"
      />
    </label>
  );
}
