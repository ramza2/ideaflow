import { useState } from "react";
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
import { MOCK_IDEAS } from "../../mocks/ideas";
import { getUserById } from "../../mocks/users";
import { Button } from "../../components/common/Button";
import { StageBadge } from "../../components/common/Badge";
import { Avatar } from "../../components/common/Avatar";
import { EmptyState } from "../../components/common/EmptyState";
import type { IdeaStage } from "../../types";

type ReviewTab = "scheduled" | "overdue" | "needs_info" | "next_stage" | "assigned" | "mentioned";

const REVIEW_TABS: { id: ReviewTab; label: string }[] = [
  { id: "scheduled", label: "검토 예정" },
  { id: "overdue", label: "검토일 경과" },
  { id: "needs_info", label: "내용 보완 필요" },
  { id: "next_stage", label: "다음 단계 후보" },
  { id: "assigned", label: "내가 담당" },
  { id: "mentioned", label: "나를 언급" },
];

const REASON_LABELS: Record<string, { label: string; color: string; icon: any }> = {
  scheduled: { label: "검토 예정", color: "#4f46e5", icon: Calendar },
  overdue: { label: "검토일 경과", color: "#dc2626", icon: AlertCircle },
  needs_info: { label: "내용 보완 필요", color: "#d97706", icon: AlertCircle },
  next_stage: { label: "다음 단계 후보", color: "#16a34a", icon: ChevronRight },
  assigned: { label: "내가 담당", color: "#7c3aed", icon: Check },
  mentioned: { label: "나를 언급", color: "#0891b2", icon: MessageSquare },
};

interface ReviewItem {
  ideaId: string;
  reason: string;
  dueDate: string;
  daysLeft?: number;
}

const MOCK_REVIEW_ITEMS: ReviewItem[] = [
  { ideaId: "idea-008", reason: "scheduled", dueDate: "2026-07-28", daysLeft: 5 },
  { ideaId: "idea-004", reason: "overdue", dueDate: "2026-06-23", daysLeft: -30 },
  { ideaId: "idea-001", reason: "needs_info", dueDate: "2026-08-01", daysLeft: 9 },
  { ideaId: "idea-005", reason: "next_stage", dueDate: "2026-08-10", daysLeft: 17 },
  { ideaId: "idea-007", reason: "assigned", dueDate: "2026-07-30", daysLeft: 7 },
];

export function ReviewsPage() {
  const navigate = useNavigate();
  const { workspaceId = "personal" } = useParams();
  const [tab, setTab] = useState<ReviewTab>("scheduled");
  const [showModal, setShowModal] = useState(false);
  const [selectedIdea, setSelectedIdea] = useState<string | null>(null);

  const filtered = MOCK_REVIEW_ITEMS.filter(
    (item) => tab === "scheduled" || item.reason === tab || tab === "overdue" && item.daysLeft !== undefined && item.daysLeft < 0
  );

  function openReviewModal(ideaId: string) {
    setSelectedIdea(ideaId);
    setShowModal(true);
  }

  return (
    <div className="flex flex-col h-full">
      {/* Header */}
      <div className="px-4 sm:px-8 pt-6 pb-4 bg-white border-b border-[rgba(0,0,0,0.06)]">
        <div className="flex items-center justify-between mb-4">
          <div>
            <h1 className="text-xl font-bold text-[#111118]">검토함</h1>
            <p className="text-sm text-[#6b6b80]">미처리 {MOCK_REVIEW_ITEMS.length}건</p>
          </div>
          <div className="flex items-center gap-2">
            <Button variant="ghost" size="sm" icon={<Filter className="w-3.5 h-3.5" />}>필터</Button>
            <Button variant="ghost" size="sm" icon={<SlidersHorizontal className="w-3.5 h-3.5" />}>정렬</Button>
          </div>
        </div>
        <div className="flex gap-0.5 -mb-px overflow-x-auto">
          {REVIEW_TABS.map((t) => {
            const count = MOCK_REVIEW_ITEMS.filter((i) => i.reason === t.id).length;
            return (
              <button
                key={t.id}
                onClick={() => setTab(t.id)}
                className={clsx(
                  "flex items-center gap-1.5 px-3 py-2 text-sm font-medium border-b-2 whitespace-nowrap transition-colors",
                  tab === t.id
                    ? "border-[#4f46e5] text-[#4f46e5]"
                    : "border-transparent text-[#6b6b80] hover:text-[#111118]"
                )}
              >
                {t.label}
                {count > 0 && (
                  <span className={clsx(
                    "text-xs px-1.5 py-0.5 rounded-full font-medium",
                    tab === t.id ? "bg-[#ede9fe] text-[#4f46e5]" : "bg-[#f0f0f5] text-[#6b6b80]"
                  )}>
                    {count}
                  </span>
                )}
              </button>
            );
          })}
        </div>
      </div>

      {/* List */}
      <div className="flex-1 overflow-y-auto px-4 sm:px-8 py-5">
        {filtered.length === 0 ? (
          <EmptyState
            icon={<Check className="w-6 h-6" />}
            title="모두 완료되었습니다!"
            description="이 탭에 검토할 항목이 없습니다."
          />
        ) : (
          <div className="space-y-3">
            {filtered.map((item) => {
              const idea = MOCK_IDEAS.find((i) => i.id === item.ideaId);
              if (!idea) return null;
              const author = getUserById(idea.authorId);
              const reason = REASON_LABELS[item.reason];
              const isOverdue = item.daysLeft !== undefined && item.daysLeft < 0;

              return (
                <div
                  key={item.ideaId}
                  className="bg-white rounded-xl border border-[rgba(0,0,0,0.07)] p-4 hover:border-[rgba(0,0,0,0.12)] transition-all group"
                >
                  <div className="flex items-start gap-3">
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center gap-2 mb-1.5">
                        <StageBadge stage={idea.stage} />
                        <span
                          className="text-xs font-medium px-2 py-0.5 rounded-full"
                          style={{ color: reason.color, backgroundColor: reason.color + "18" }}
                        >
                          {reason.label}
                        </span>
                      </div>
                      <button
                        onClick={() => navigate(`/w/${workspaceId}/ideas/${idea.id}`)}
                        className="text-sm font-semibold text-[#111118] hover:text-[#4f46e5] text-left block mb-0.5"
                      >
                        {idea.title}
                      </button>
                      <p className="text-xs text-[#6b6b80] mb-2">{idea.oneLiner}</p>
                      <div className="flex items-center gap-3 text-xs text-[#9ca3af]">
                        {author && (
                          <div className="flex items-center gap-1">
                            <Avatar user={author} size="xs" />
                            {author.name}
                          </div>
                        )}
                        <div className={clsx(
                          "flex items-center gap-1",
                          isOverdue ? "text-[#dc2626]" : "text-[#9ca3af]"
                        )}>
                          <Clock className="w-3 h-3" />
                          {isOverdue
                            ? `${Math.abs(item.daysLeft!)}일 경과`
                            : `${item.daysLeft}일 후`}
                        </div>
                      </div>
                    </div>

                    {/* Quick actions */}
                    <div className="flex items-center gap-1.5 shrink-0 opacity-0 group-hover:opacity-100 transition-opacity">
                      <button
                        onClick={() => navigate(`/w/${workspaceId}/ideas/${idea.id}`)}
                        className="text-xs px-2.5 py-1.5 rounded-lg border border-[rgba(0,0,0,0.1)] text-[#6b6b80] hover:bg-[#f4f4f8] transition-colors"
                      >
                        상세 보기
                      </button>
                      <button
                        onClick={() => openReviewModal(idea.id)}
                        className="text-xs px-2.5 py-1.5 rounded-lg bg-[#4f46e5] text-white hover:bg-[#4338ca] transition-colors"
                      >
                        검토 완료
                      </button>
                      <button className="w-7 h-7 flex items-center justify-center rounded-lg text-[#9ca3af] hover:bg-[#f4f4f8]">
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

      {/* Review complete modal */}
      {showModal && (
        <div className="fixed inset-0 bg-black/30 z-50 flex items-center justify-center p-4">
          <div className="bg-white rounded-2xl border border-[rgba(0,0,0,0.08)] shadow-xl w-full max-w-md p-6">
            <h3 className="text-base font-bold text-[#111118] mb-4">검토 완료</h3>
            <div className="space-y-4">
              <div>
                <label className="text-sm font-medium text-[#111118] block mb-1.5">검토 결과</label>
                <div className="flex gap-2 flex-wrap">
                  {["다음 단계로 이동", "현 단계 유지", "보류", "보완 필요"].map((opt) => (
                    <button
                      key={opt}
                      className="px-3 py-1.5 text-sm rounded-lg border border-[rgba(0,0,0,0.1)] text-[#6b6b80] hover:border-[#4f46e5] hover:text-[#4f46e5] transition-colors"
                    >
                      {opt}
                    </button>
                  ))}
                </div>
              </div>
              <div>
                <label className="text-sm font-medium text-[#111118] block mb-1.5">검토 메모</label>
                <textarea
                  className="w-full h-20 rounded-lg border border-[rgba(0,0,0,0.1)] bg-white px-3 py-2 text-sm resize-none focus:outline-none focus:ring-2 focus:ring-[#4f46e5]/20 focus:border-[#4f46e5]"
                  placeholder="검토 내용을 간단히 기록하세요 (선택사항)"
                />
              </div>
              <div>
                <label className="text-sm font-medium text-[#111118] block mb-1.5">다음 검토일</label>
                <input type="date" className="h-9 rounded-lg border border-[rgba(0,0,0,0.1)] bg-white px-3 text-sm focus:outline-none focus:ring-2 focus:ring-[#4f46e5]/20 focus:border-[#4f46e5]" />
              </div>
            </div>
            <div className="flex gap-2 mt-5">
              <Button variant="ghost" className="flex-1" onClick={() => setShowModal(false)}>취소</Button>
              <Button variant="primary" className="flex-1" onClick={() => setShowModal(false)}>
                완료 저장
              </Button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
