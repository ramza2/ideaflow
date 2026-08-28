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

/* --- Step 8: AI Session --- */

export type AiSessionPurpose = "CREATE" | "REFINE" | "RESEARCH";

export type AiSessionStatus =
  | "PROCESSING"
  | "NEEDS_CLARIFICATION"
  | "READY_FOR_REVIEW"
  | "CONFIRMED"
  | "FAILED"
  | "CANCELLED";

export type AiFieldProvenanceSource =
  | "USER_INPUT"
  | "LLM_SUMMARY"
  | "LLM_INFERENCE"
  | "WEB_EVIDENCE"
  | "USER_EDIT";

export interface AiDraft {
  title?: string | null;
  one_line_definition?: string | null;
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
  category_slug?: string | null;
  priority?: IdeaPriority | null;
  feasibility?: IdeaFeasibility | null;
  tags?: string[];
}

export interface AiFieldProvenance {
  source?: AiFieldProvenanceSource | string;
  note?: string | null;
  original_source?: string | null;
  final_source?: string | null;
}

export interface AiClarifyingQuestion {
  id: string;
  field?: string | null;
  question: string;
}

export interface AiClarificationAnswer {
  question_id: string;
  answer: string;
}

export interface AiSessionFailure {
  code: string;
  message: string;
}

export interface AiSessionLlm {
  provider: string | null;
  model: string | null;
  prompt_version: string | null;
}

export interface AiSession {
  id: string;
  workspace_id: string;
  purpose: AiSessionPurpose;
  status: AiSessionStatus;
  input_text: string;
  draft: AiDraft | null;
  field_provenance: Record<string, AiFieldProvenance> | null;
  clarifying_questions: AiClarifyingQuestion[] | null;
  clarification_answers: AiClarificationAnswer[] | null;
  research_recommended: boolean;
  research_topics: string[] | null;
  result_idea_id: string | null;
  failure: AiSessionFailure | null;
  llm: AiSessionLlm;
  created_at: string;
  updated_at: string;
  ready_at: string | null;
  confirmed_at: string | null;
}

export interface AiSessionCreateRequest {
  purpose?: AiSessionPurpose;
  input_text: string;
}

export interface AiClarificationSubmitRequest {
  answers: AiClarificationAnswer[];
}

export interface AiSessionConfirmRequest {
  title: string;
  one_line_definition?: string | null;
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

export interface AiSessionConfirmResponse {
  created: boolean;
  idea: IdeaDetail;
}
