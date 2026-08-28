import { useCallback, useEffect, useRef, useState } from "react";
import { useNavigate, useParams } from "react-router";
import { clsx } from "clsx";
import {
  Filter,
  SlidersHorizontal,
  ChevronRight,
  Check,
  Calendar,
  ChevronDown,
  MessageSquare,
  AlertCircle,
  Clock,
} from "lucide-react";
import { completeReview, getReviewInbox, getReviewInboxCounts } from "../../api/reviews";
import { apiErrorMessage } from "../../api/client";
import { Button } from "../../components/common/Button";
import { StageLabelBadge } from "../../components/common/Badge";
import { Avatar } from "../../components/common/Avatar";
import { EmptyState } from "../../components/common/EmptyState";
import { toast } from "../../components/common/Toast";
import { toDisplayUser } from "../../utils/avatar";
import {
  REVIEW_RESULT_OPTIONS,
  dispatchReviewCountsChanged,
} from "../../utils/collaboration";
import { inboxRequestKey, shouldApplyRequest } from "../../utils/requestFence";
import type {
  ReviewInboxCounts,
  ReviewInboxItem,
  ReviewInboxTab,
  ReviewResult,
} from "../../types/api";

const REVIEW_TABS: { id: ReviewInboxTab; label: string }[] = [
  { id: "scheduled", label: "검토 예정" },
  { id: "overdue", label: "검토일 경과" },
  { id: "needs_info", label: "내용 보완 필요" },
  { id: "next_stage", label: "다음 단계 후보" },
  { id: "assigned", label: "내가 담당" },
  { id: "mentioned", label: "나를 언급" },
];

const REASON_LABELS: Record<string, { label: string; color: string; icon: typeof Calendar }> = {
  scheduled: { label: "검토 예정", color: "#4f46e5", icon: Calendar },
  overdue: { label: "검토일 경과", color: "#dc2626", icon: AlertCircle },
  needs_info: { label: "내용 보완 필요", color: "#d97706", icon: AlertCircle },
  next_stage: { label: "다음 단계 후보", color: "#16a34a", icon: ChevronRight },
  assigned: { label: "내가 담당", color: "#7c3aed", icon: Check },
  mentioned: { label: "나를 언급", color: "#0891b2", icon: MessageSquare },
};

function daysUntil(dueDate: string | null | undefined): number | null {
  if (!dueDate) return null;
  const today = new Date();
  today.setHours(0, 0, 0, 0);
  const due = new Date(dueDate + "T00:00:00");
  return Math.round((due.getTime() - today.getTime()) / (1000 * 60 * 60 * 24));
}

export function ReviewsPage() {
  const navigate = useNavigate();
  const { workspaceId = "" } = useParams();
  const [tab, setTab] = useState<ReviewInboxTab>("scheduled");
  const [items, setItems] = useState<ReviewInboxItem[]>([]);
  const [counts, setCounts] = useState<ReviewInboxCounts | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [showModal, setShowModal] = useState(false);
  const [selectedReview, setSelectedReview] = useState<ReviewInboxItem | null>(null);
  const [selectedResult, setSelectedResult] = useState<ReviewResult>("ADVANCE_RECOMMENDED");
  const [completionNote, setCompletionNote] = useState("");
  const [suggestedDate, setSuggestedDate] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const activeRequestKeyRef = useRef(inboxRequestKey(workspaceId, tab));

  useEffect(() => {
    const requestKey = inboxRequestKey(workspaceId, tab);
    activeRequestKeyRef.current = requestKey;
    setItems([]);
    setCounts(null);
    setLoading(true);
    setError(null);
  }, [workspaceId, tab]);

  const loadInbox = useCallback(async () => {
    const requestKey = inboxRequestKey(workspaceId, tab);
    if (!workspaceId) return;
    setLoading(true);
    setError(null);
    try {
      const [inbox, countData] = await Promise.all([
        getReviewInbox(workspaceId, tab),
        getReviewInboxCounts(workspaceId),
      ]);
      if (!shouldApplyRequest(activeRequestKeyRef.current, requestKey)) return;
      setItems(inbox.items);
      setCounts(countData);
    } catch (err) {
      if (!shouldApplyRequest(activeRequestKeyRef.current, requestKey)) return;
      setError(apiErrorMessage(err, "검토함을 불러오지 못했습니다."));
      setItems([]);
    } finally {
      if (!shouldApplyRequest(activeRequestKeyRef.current, requestKey)) return;
      setLoading(false);
    }
  }, [workspaceId, tab]);

  useEffect(() => {
    void loadInbox();
  }, [loadInbox]);

  function openReviewModal(item: ReviewInboxItem) {
    setSelectedReview(item);
    setSelectedResult("ADVANCE_RECOMMENDED");
    setCompletionNote("");
    setSuggestedDate("");
    setShowModal(true);
  }

  async function handleComplete() {
    if (!workspaceId || !selectedReview?.review_request) return;
    setSubmitting(true);
    try {
      await completeReview(workspaceId, selectedReview.review_request.id, {
        result: selectedResult,
        completion_note: completionNote.trim() || null,
        suggested_next_review_date: suggestedDate || null,
      });
      toast.success("검토를 완료했습니다.");
      setShowModal(false);
      setSelectedReview(null);
      await loadInbox();
      dispatchReviewCountsChanged();
    } catch (err) {
      toast.error(apiErrorMessage(err, "검토 완료에 실패했습니다."));
    } finally {
      setSubmitting(false);
    }
  }

  function tabCount(tabId: ReviewInboxTab): number {
    if (!counts) return 0;
    return counts[tabId];
  }

  function handleItemClick(item: ReviewInboxItem) {
    if (item.reason === "mentioned") {
      navigate(`/w/${workspaceId}/ideas/${item.idea.id}?tab=discussion`);
      return;
    }
    navigate(`/w/${workspaceId}/ideas/${item.idea.id}`);
  }

  return (
    <div className="flex flex-col h-full">
      <div className="px-4 sm:px-8 pt-6 pb-4 bg-white border-b border-[rgba(0,0,0,0.06)]">
        <div className="flex items-center justify-between mb-4">
          <div>
            <h1 className="text-xl font-bold text-[#111118]">검토함</h1>
            <p className="text-sm text-[#6b6b80]">
              미처리 {counts?.pending_total ?? 0}건
            </p>
          </div>
          <div className="flex items-center gap-2">
            <Button
              variant="ghost"
              size="sm"
              icon={<Filter className="w-3.5 h-3.5" />}
              disabled
              title="추후 제공됩니다."
            >
              필터
            </Button>
            <Button
              variant="ghost"
              size="sm"
              icon={<SlidersHorizontal className="w-3.5 h-3.5" />}
              disabled
              title="추후 제공됩니다."
            >
              정렬
            </Button>
          </div>
        </div>
        <div className="flex gap-0.5 -mb-px overflow-x-auto">
          {REVIEW_TABS.map((t) => {
            const count = tabCount(t.id);
            return (
              <button
                key={t.id}
                onClick={() => setTab(t.id)}
                className={clsx(
                  "flex items-center gap-1.5 px-3 py-2 text-sm font-medium border-b-2 whitespace-nowrap transition-colors",
                  tab === t.id
                    ? "border-[#4f46e5] text-[#4f46e5]"
                    : "border-transparent text-[#6b6b80] hover:text-[#111118]",
                )}
              >
                {t.label}
                {count > 0 && (
                  <span
                    className={clsx(
                      "text-xs px-1.5 py-0.5 rounded-full font-medium",
                      tab === t.id ? "bg-[#ede9fe] text-[#4f46e5]" : "bg-[#f0f0f5] text-[#6b6b80]",
                    )}
                  >
                    {count}
                  </span>
                )}
              </button>
            );
          })}
        </div>
      </div>

      <div className="flex-1 overflow-y-auto px-4 sm:px-8 py-5">
        {loading ? (
          <p className="text-sm text-[#6b6b80]">불러오는 중...</p>
        ) : error ? (
          <EmptyState
            icon={<AlertCircle className="w-6 h-6" />}
            title="검토함을 불러올 수 없습니다"
            description={error}
            action={
              <Button variant="secondary" size="sm" onClick={() => void loadInbox()}>
                다시 시도
              </Button>
            }
          />
        ) : items.length === 0 ? (
          <EmptyState
            icon={<Check className="w-6 h-6" />}
            title="모두 완료되었습니다!"
            description="이 탭에 검토할 항목이 없습니다."
          />
        ) : (
          <div className="space-y-3">
            {items.map((item) => {
              const reason = REASON_LABELS[item.reason] ?? REASON_LABELS.scheduled;
              const dueDate = item.review_request?.due_date;
              const daysLeft = daysUntil(dueDate);
              const isOverdue = daysLeft !== null && daysLeft < 0;
              const author = item.idea.author ? toDisplayUser(item.idea.author) : null;
              const canComplete = item.source === "REVIEW_REQUEST" && item.review_request;

              return (
                <div
                  key={`${item.source}-${item.review_request?.id ?? item.comment?.id ?? item.idea.id}`}
                  className="bg-white rounded-xl border border-[rgba(0,0,0,0.07)] p-4 hover:border-[rgba(0,0,0,0.12)] transition-all group"
                >
                  <div className="flex items-start gap-3">
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center gap-2 mb-1.5">
                        {item.idea.stage && <StageLabelBadge label={item.idea.stage.label} />}
                        <span
                          className="text-xs font-medium px-2 py-0.5 rounded-full"
                          style={{ color: reason.color, backgroundColor: reason.color + "18" }}
                        >
                          {reason.label}
                        </span>
                      </div>
                      <button
                        type="button"
                        onClick={() => handleItemClick(item)}
                        className="text-sm font-semibold text-[#111118] hover:text-[#4f46e5] text-left block mb-0.5"
                      >
                        {item.idea.title}
                      </button>
                      <p className="text-xs text-[#6b6b80] mb-2">
                        {item.idea.one_line_definition ?? ""}
                      </p>
                      {item.comment && (
                        <p className="text-xs text-[#6b6b80] bg-[#f4f4f8] rounded-lg px-3 py-2 mb-2 line-clamp-2">
                          {item.comment.body}
                        </p>
                      )}
                      <div className="flex items-center gap-3 text-xs text-[#9ca3af]">
                        {author && (
                          <div className="flex items-center gap-1">
                            <Avatar user={author} size="xs" />
                            {author.name}
                          </div>
                        )}
                        {daysLeft !== null && (
                          <div
                            className={clsx(
                              "flex items-center gap-1",
                              isOverdue ? "text-[#dc2626]" : "text-[#9ca3af]",
                            )}
                          >
                            <Clock className="w-3 h-3" />
                            {isOverdue
                              ? `${Math.abs(daysLeft)}일 경과`
                              : daysLeft === 0
                                ? "오늘"
                                : `${daysLeft}일 후`}
                          </div>
                        )}
                      </div>
                    </div>

                    <div className="flex items-center gap-1.5 shrink-0 opacity-0 group-hover:opacity-100 transition-opacity">
                      <button
                        type="button"
                        onClick={() => handleItemClick(item)}
                        className="text-xs px-2.5 py-1.5 rounded-lg border border-[rgba(0,0,0,0.1)] text-[#6b6b80] hover:bg-[#f4f4f8] transition-colors"
                      >
                        상세 보기
                      </button>
                      {canComplete && (
                        <button
                          type="button"
                          onClick={() => openReviewModal(item)}
                          className="text-xs px-2.5 py-1.5 rounded-lg bg-[#4f46e5] text-white hover:bg-[#4338ca] transition-colors"
                        >
                          검토 완료
                        </button>
                      )}
                      <button
                        type="button"
                        disabled
                        title="추후 제공됩니다."
                        className="w-7 h-7 flex items-center justify-center rounded-lg text-[#9ca3af] opacity-50 cursor-not-allowed"
                      >
                        <ChevronDown className="w-4 h-4" />
                      </button>
                    </div>
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </div>

      {showModal && selectedReview && (
        <div className="fixed inset-0 bg-black/30 z-50 flex items-center justify-center p-4">
          <div className="bg-white rounded-2xl border border-[rgba(0,0,0,0.08)] shadow-xl w-full max-w-md p-6">
            <h3 className="text-base font-bold text-[#111118] mb-4">검토 완료</h3>
            <div className="space-y-4">
              <div>
                <label className="text-sm font-medium text-[#111118] block mb-1.5">검토 결과</label>
                <div className="flex gap-2 flex-wrap">
                  {REVIEW_RESULT_OPTIONS.map((opt) => (
                    <button
                      key={opt.value}
                      type="button"
                      onClick={() => setSelectedResult(opt.value)}
                      className={clsx(
                        "px-3 py-1.5 text-sm rounded-lg border transition-colors",
                        selectedResult === opt.value
                          ? "border-[#4f46e5] text-[#4f46e5] bg-[#f5f3ff]"
                          : "border-[rgba(0,0,0,0.1)] text-[#6b6b80] hover:border-[#4f46e5] hover:text-[#4f46e5]",
                      )}
                    >
                      {opt.label}
                    </button>
                  ))}
                </div>
              </div>
              <div>
                <label className="text-sm font-medium text-[#111118] block mb-1.5">검토 메모</label>
                <textarea
                  value={completionNote}
                  onChange={(e) => setCompletionNote(e.target.value)}
                  className="w-full h-20 rounded-lg border border-[rgba(0,0,0,0.1)] bg-white px-3 py-2 text-sm resize-none focus:outline-none focus:ring-2 focus:ring-[#4f46e5]/20 focus:border-[#4f46e5]"
                  placeholder="검토 내용을 간단히 기록하세요 (선택사항)"
                />
              </div>
              <div>
                <label className="text-sm font-medium text-[#111118] block mb-1.5">
                  다음 검토일 제안
                </label>
                <input
                  type="date"
                  value={suggestedDate}
                  onChange={(e) => setSuggestedDate(e.target.value)}
                  className="h-9 rounded-lg border border-[rgba(0,0,0,0.1)] bg-white px-3 text-sm focus:outline-none focus:ring-2 focus:ring-[#4f46e5]/20 focus:border-[#4f46e5]"
                />
              </div>
            </div>
            <div className="flex gap-2 mt-5">
              <Button variant="ghost" className="flex-1" onClick={() => setShowModal(false)} disabled={submitting}>
                취소
              </Button>
              <Button
                variant="primary"
                className="flex-1"
                loading={submitting}
                disabled={submitting}
                onClick={() => void handleComplete()}
              >
                완료 저장
              </Button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
