/** Backend API contract types (snake_case / UPPER enums). */

export type UserStatus = "ACTIVE" | "INACTIVE" | "LOCKED" | "WITHDRAWN";
export type SystemRole = "SYSTEM_ADMIN" | "USER";
export type WorkspaceType = "PERSONAL" | "TEAM";
export type WorkspaceRole = "ADMIN" | "MEMBER" | "VIEWER";
export type WorkspaceMemberStatus = "PENDING" | "ACTIVE" | "INACTIVE";
export type IdeaPriority = "HIGH" | "MEDIUM" | "LOW";
export type IdeaFeasibility = "HIGH" | "MEDIUM" | "LOW" | "UNKNOWN";
export type IdeaVisibility = "PRIVATE" | "WORKSPACE" | "SELECTED_USERS";
export type IdeaSharePermission = "READ" | "EDIT";
export type IdeaAccess = "OWNER" | "EDIT" | "READ";

export interface UserPublic {
  id: string;
  email: string;
  name: string;
  status: UserStatus;
  system_role: SystemRole;
  must_change_password: boolean;
}

export interface SessionInfo {
  expires_at: string;
  absolute_expires_at: string;
}

export interface LoginResponse {
  user: UserPublic;
  session: SessionInfo;
}

export interface CsrfResponse {
  csrf_token: string;
}

export interface WorkspacePublic {
  id: string;
  name: string;
  type: WorkspaceType;
  owner_id: string;
  allow_llm: boolean;
  allow_web_search: boolean;
  current_user_role: WorkspaceRole;
  created_at: string;
  updated_at: string;
}

export interface TeamWorkspaceCreate {
  name: string;
  allow_llm?: boolean;
  allow_web_search?: boolean;
}

export interface MemberPublic {
  user_id: string;
  email: string;
  name: string;
  role: WorkspaceRole;
  status: WorkspaceMemberStatus;
  created_at: string;
  updated_at: string;
}

export interface MemberAddRequest {
  email: string;
  role?: WorkspaceRole;
}

export interface MemberRoleUpdate {
  role: WorkspaceRole;
}

export interface StagePublic {
  id: string;
  slug: string;
  label: string;
  sort_order: number;
  is_default: boolean;
  is_terminal: boolean;
}

export interface CategoryPublic {
  id: string;
  slug: string;
  name: string;
  sort_order: number;
}

export interface IdeaUserRef {
  id: string;
  name: string;
}

export interface TagRef {
  id: string;
  name: string;
}

export interface StageRef {
  id: string;
  slug: string;
  label: string;
}

export interface CategoryRef {
  id: string;
  slug: string;
  name: string;
}

export interface IdeaListItem {
  id: string;
  idea_code: string;
  title: string;
  one_line_definition: string | null;
  category: CategoryRef | null;
  stage: StageRef;
  priority: IdeaPriority;
  feasibility: IdeaFeasibility;
  visibility: IdeaVisibility;
  author: IdeaUserRef;
  assignee: IdeaUserRef | null;
  tags: TagRef[];
  next_review_date: string | null;
  created_at: string;
  updated_at: string;
  current_user_access: IdeaAccess;
}

export interface IdeaDetail extends IdeaListItem {
  workspace_id: string;
  original_text: string | null;
  background: string | null;
  problem: string | null;
  core_concept: string | null;
  major_features: string | null;
  expected_effect: string | null;
  target_users: string | null;
  scenarios: string | null;
  challenges: string | null;
  minimum_validation: string | null;
  related_project: string | null;
}

export interface IdeaListResponse {
  items: IdeaListItem[];
  total: number;
  limit: number;
  offset: number;
}

export interface IdeaShareInput {
  user_id: string;
  permission: IdeaSharePermission;
}

export interface IdeaSharePublic {
  user_id: string;
  name: string;
  permission: IdeaSharePermission;
}

export interface IdeaCreateRequest {
  title: string;
  one_line_definition?: string | null;
  original_text?: string | null;
  background?: string | null;
  problem?: string | null;
  core_concept?: string | null;
  major_features?: string | null;
  expected_effect?: string | null;
  target_users?: string | null;
  scenarios?: string | null;
  challenges?: string | null;
  minimum_validation?: string | null;
  related_project?: string | null;
  category_id?: string | null;
  stage_id?: string | null;
  priority?: IdeaPriority;
  feasibility?: IdeaFeasibility;
  visibility?: IdeaVisibility;
  assignee_id?: string | null;
  next_review_date?: string | null;
  tags?: string[];
  shares?: IdeaShareInput[] | null;
}

export type IdeaUpdateRequest = Partial<
  Omit<IdeaCreateRequest, "shares">
>;

export interface IdeaListParams {
  q?: string;
  stage_id?: string;
  category_id?: string;
  priority?: IdeaPriority;
  feasibility?: IdeaFeasibility;
  visibility?: IdeaVisibility;
  author_id?: string;
  assignee_id?: string;
  limit?: number;
  offset?: number;
}
