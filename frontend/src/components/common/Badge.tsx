import { clsx } from "clsx";
import type { IdeaStage, Priority, Feasibility, Visibility, SourceBadgeType, MemberStatus, MemberRole } from "../../types";

interface BadgeProps {
  children: React.ReactNode;
  className?: string;
  variant?: "default" | "outline";
}

export function Badge({ children, className, variant = "default" }: BadgeProps) {
  return (
    <span
      className={clsx(
        "inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-medium",
        variant === "outline" && "border",
        className
      )}
    >
      {children}
    </span>
  );
}

const stageConfig: Record<IdeaStage, { label: string; className: string }> = {
  draft: { label: "초안", className: "bg-[#f0f0f5] text-[#6b6b80]" },
  reviewing: { label: "검토 중", className: "bg-[#fffbeb] text-[#d97706]" },
  validated: { label: "검증 후보", className: "bg-[#ede9fe] text-[#7c3aed]" },
  executing: { label: "실행 중", className: "bg-[#f0fdf4] text-[#16a34a]" },
  paused: { label: "보류", className: "bg-[#f0f0f5] text-[#6b6b80]" },
  archived: { label: "보관", className: "bg-[#f0f0f5] text-[#9ca3af]" },
};

export function StageBadge({ stage }: { stage: IdeaStage }) {
  const cfg = stageConfig[stage];
  return (
    <Badge className={cfg.className}>{cfg.label}</Badge>
  );
}

const priorityConfig: Record<Priority, { label: string; className: string; dot: string }> = {
  high: { label: "높음", className: "bg-[#fef2f2] text-[#dc2626]", dot: "bg-[#dc2626]" },
  medium: { label: "중간", className: "bg-[#fffbeb] text-[#d97706]", dot: "bg-[#d97706]" },
  low: { label: "낮음", className: "bg-[#f0f0f5] text-[#6b6b80]", dot: "bg-[#9ca3af]" },
};

export function PriorityBadge({ priority }: { priority: Priority }) {
  const cfg = priorityConfig[priority];
  return (
    <Badge className={cfg.className}>
      <span className={clsx("w-1.5 h-1.5 rounded-full", cfg.dot)} />
      {cfg.label}
    </Badge>
  );
}

const feasibilityConfig: Record<Feasibility, { label: string; className: string }> = {
  high: { label: "높음", className: "bg-[#f0fdf4] text-[#16a34a]" },
  medium: { label: "중간", className: "bg-[#fffbeb] text-[#d97706]" },
  low: { label: "낮음", className: "bg-[#fef2f2] text-[#dc2626]" },
  unknown: { label: "미평가", className: "bg-[#f0f0f5] text-[#6b6b80]" },
};

export function FeasibilityBadge({ feasibility }: { feasibility: Feasibility }) {
  const cfg = feasibilityConfig[feasibility];
  return <Badge className={cfg.className}>{cfg.label}</Badge>;
}

const visibilityConfig: Record<Visibility, { label: string; className: string }> = {
  private: { label: "비공개", className: "bg-[#f0f0f5] text-[#6b6b80]" },
  workspace: { label: "작업공간", className: "bg-[#ede9fe] text-[#7c3aed]" },
  specific: { label: "지정 공유", className: "bg-[#dbeafe] text-[#2563eb]" },
};

export function VisibilityBadge({ visibility }: { visibility: Visibility }) {
  const cfg = visibilityConfig[visibility];
  return <Badge className={cfg.className}>{cfg.label}</Badge>;
}

const sourceConfig: Record<SourceBadgeType, { label: string; className: string }> = {
  user_input: { label: "사용자 입력", className: "bg-[#f0f0f5] text-[#6b6b80] border border-[rgba(0,0,0,0.08)]" },
  llm_structured: { label: "LLM 정리", className: "bg-[#ede9fe] text-[#7c3aed] border border-[#ddd6fe]" },
  llm_inferred: { label: "LLM 추론", className: "bg-[#f5f3ff] text-[#7c3aed] border border-[#ede9fe]" },
  web_evidence: { label: "웹 근거", className: "bg-[#dbeafe] text-[#2563eb] border border-[#bfdbfe]" },
  user_edited: { label: "사용자 수정", className: "bg-[#f0fdf4] text-[#16a34a] border border-[#bbf7d0]" },
};

export function SourceBadge({ type }: { type: SourceBadgeType }) {
  const cfg = sourceConfig[type];
  return <Badge variant="outline" className={cfg.className}>{cfg.label}</Badge>;
}

const memberStatusConfig: Record<MemberStatus, { label: string; className: string }> = {
  active: { label: "참여 중", className: "bg-[#f0fdf4] text-[#16a34a]" },
  pending: { label: "초대 대기", className: "bg-[#fffbeb] text-[#d97706]" },
  inactive: { label: "비활성", className: "bg-[#f0f0f5] text-[#6b6b80]" },
};

export function MemberStatusBadge({ status }: { status: MemberStatus }) {
  const cfg = memberStatusConfig[status];
  return <Badge className={cfg.className}>{cfg.label}</Badge>;
}

const memberRoleConfig: Record<MemberRole, { label: string }> = {
  admin: { label: "작업공간 관리자" },
  member: { label: "일반 구성원" },
  readonly: { label: "읽기 전용" },
};

export function MemberRoleBadge({ role }: { role: MemberRole }) {
  return <span className="text-sm text-[#6b6b80]">{memberRoleConfig[role].label}</span>;
}
