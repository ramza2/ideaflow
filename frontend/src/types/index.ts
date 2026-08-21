export type IdeaStage =
  | "draft"
  | "reviewing"
  | "validated"
  | "executing"
  | "paused"
  | "archived";

export type Priority = "high" | "medium" | "low";
export type Feasibility = "high" | "medium" | "low" | "unknown";
export type Visibility = "private" | "workspace" | "specific";
export type MemberRole = "admin" | "member" | "readonly";
export type MemberStatus = "active" | "pending" | "inactive";
export type SourceBadgeType =
  | "user_input"
  | "llm_structured"
  | "llm_inferred"
  | "web_evidence"
  | "user_edited";

export interface User {
  id: string;
  name: string;
  email: string;
  avatarInitials: string;
  avatarColor: string;
  role: "user" | "admin";
}

export interface Workspace {
  id: string;
  name: string;
  type: "personal" | "team";
  icon: string;
}

export interface Tag {
  id: string;
  label: string;
  color: string;
}

export interface Idea {
  id: string;
  code: string;
  title: string;
  oneLiner: string;
  field: string;
  tags: string[];
  stage: IdeaStage;
  priority: Priority;
  feasibility: Feasibility;
  visibility: Visibility;
  authorId: string;
  assigneeId?: string;
  participantIds: string[];
  nextReviewDate?: string;
  createdAt: string;
  updatedAt: string;
  workspaceId: string;
  isFavorite: boolean;
  commentCount: number;
  background?: string;
  problem?: string;
  concept?: string;
  features?: string;
  expectedEffect?: string;
  targetUsers?: string;
  scenario?: string;
  challenges?: string;
  validationMethod?: string;
  relatedProject?: string;
}

export interface Notification {
  id: string;
  type: "comment" | "assigned" | "review_due" | "ai_done" | "workspace_invite";
  title: string;
  body: string;
  ideaId?: string;
  createdAt: string;
  read: boolean;
}

export interface EvidenceSource {
  id: string;
  title: string;
  publisher: string;
  publishedAt: string;
  fetchedAt: string;
  type: "article" | "paper" | "official" | "blog";
  summary: string;
  url: string;
  relatedFields: string[];
  status: "applied" | "partial" | "reference" | "excluded" | "needs_check";
}

export interface ReviewItem {
  id: string;
  ideaId: string;
  reason: "scheduled" | "overdue" | "needs_info" | "next_stage" | "assigned" | "mentioned";
  dueDate: string;
  assigneeId?: string;
}

export interface Member {
  userId: string;
  workspaceId: string;
  role: MemberRole;
  status: MemberStatus;
  joinedAt: string;
  lastActiveAt: string;
}

export interface Comment {
  id: string;
  ideaId: string;
  authorId: string;
  body: string;
  createdAt: string;
  parentId?: string;
}

export interface HistoryEntry {
  id: string;
  ideaId: string;
  type:
    | "created"
    | "updated"
    | "stage_changed"
    | "ai_structured"
    | "web_searched"
    | "assigned"
    | "commented"
    | "exported";
  actorId: string;
  description: string;
  createdAt: string;
}
