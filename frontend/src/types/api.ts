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
  effective_allow_llm: boolean;
  effective_allow_web_search: boolean;
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
  search_mode?: "keyword" | "semantic" | "hybrid";
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

/* --- Step 9: Web Research --- */

export type WebResearchRunStatus =
  | "AWAITING_APPROVAL"
  | "QUEUED"
  | "SEARCHING"
  | "REFINING"
  | "READY"
  | "FAILED"
  | "CANCELLED";

export interface SanitizationNotePublic {
  query_index: number;
  changed: boolean;
}

export interface WebResearchFailure {
  phase?: string | null;
  code?: string | null;
  message?: string | null;
}

export interface WebEvidence {
  id: string;
  query: string;
  title: string;
  url: string;
  domain?: string | null;
  source_name?: string | null;
  snippet?: string | null;
  published_at?: string | null;
  fetched_at: string;
  rank: number;
  related_fields: string[];
}

export interface WebResearchRun {
  id: string;
  session_id: string;
  status: WebResearchRunStatus;
  queries_to_send: string[];
  sanitization_notes: SanitizationNotePublic[];
  provider?: string | null;
  result_count?: number | null;
  research_summary?: string | null;
  failure?: WebResearchFailure | null;
  evidence: WebEvidence[];
  approved_at?: string | null;
  started_at?: string | null;
  completed_at?: string | null;
  created_at: string;
  updated_at: string;
}

export interface WebResearchPreviewRequest {
  queries: string[];
  current_draft: AiDraft;
  user_edited_fields: string[];
}

export interface WebResearchLatestResponse {
  run: WebResearchRun | null;
}

export interface IdeaEvidenceItem {
  id: string;
  title: string;
  url: string;
  domain?: string | null;
  source_name?: string | null;
  snippet?: string | null;
  published_at?: string | null;
  fetched_at: string;
  related_fields: string[];
}

export interface IdeaEvidenceResponse {
  items: IdeaEvidenceItem[];
}

// --- Step 10: Review / Comment / Notification ---

export type ReviewKind = "GENERAL" | "NEEDS_INFO" | "NEXT_STAGE";
export type ReviewStatus = "OPEN" | "COMPLETED" | "CANCELLED";
export type ReviewResult = "ADVANCE_RECOMMENDED" | "KEEP" | "HOLD" | "NEEDS_INFO";

export interface UserRef {
  id: string;
  name: string;
  email: string;
}

export interface ReviewRequest {
  id: string;
  idea_id: string;
  kind: ReviewKind;
  status: ReviewStatus;
  message?: string | null;
  due_date?: string | null;
  result?: ReviewResult | null;
  completion_note?: string | null;
  suggested_next_review_date?: string | null;
  requested_by: UserRef;
  reviewer: UserRef;
  completed_at?: string | null;
  cancelled_at?: string | null;
  created_at: string;
  updated_at: string;
}

export interface ReviewCreateRequest {
  reviewer_id: string;
  kind?: ReviewKind;
  message?: string | null;
  due_date?: string | null;
}

export interface ReviewCompleteRequest {
  result: ReviewResult;
  completion_note?: string | null;
  suggested_next_review_date?: string | null;
}

export interface EligibleReviewerList {
  items: UserRef[];
}

export type ReviewInboxTab =
  | "scheduled"
  | "overdue"
  | "needs_info"
  | "next_stage"
  | "assigned"
  | "mentioned";

export interface ReviewInboxIdeaRef {
  id: string;
  idea_code: string;
  title: string;
  one_line_definition?: string | null;
  stage?: { id: string; label: string } | null;
  author?: UserRef | null;
}

export interface ReviewInboxReviewRef {
  id: string;
  kind: ReviewKind;
  due_date?: string | null;
  requested_by: UserRef;
}

export interface ReviewInboxCommentRef {
  id: string;
  body: string;
  author: UserRef;
  created_at: string;
}

export interface ReviewInboxItem {
  source: "REVIEW_REQUEST" | "COMMENT" | "IDEA";
  reason: ReviewInboxTab;
  idea: ReviewInboxIdeaRef;
  review_request?: ReviewInboxReviewRef | null;
  comment?: ReviewInboxCommentRef | null;
  created_at: string;
}

export interface ReviewInboxResponse {
  items: ReviewInboxItem[];
  total: number;
}

export interface ReviewInboxCounts {
  scheduled: number;
  overdue: number;
  needs_info: number;
  next_stage: number;
  assigned: number;
  mentioned: number;
  pending_total: number;
}

export interface CommentMention {
  id: string;
  name: string;
}

export interface IdeaComment {
  id: string;
  body: string;
  author: UserRef;
  mentions: CommentMention[];
  created_at: string;
  updated_at: string;
  edited: boolean;
  can_edit: boolean;
  can_delete: boolean;
}

export interface CommentListResponse {
  items: IdeaComment[];
  total: number;
}

export interface CommentCreateRequest {
  body: string;
  mention_user_ids?: string[];
}

export interface CommentUpdateRequest {
  body: string;
  mention_user_ids?: string[] | null;
}

export type NotificationType =
  | "REVIEW_REQUESTED"
  | "REVIEW_COMPLETED"
  | "COMMENT_ADDED"
  | "MENTION"
  | "ASSIGNED";

export interface NotificationItem {
  id: string;
  type: NotificationType;
  read: boolean;
  created_at: string;
  actor?: UserRef | null;
  idea?: ReviewInboxIdeaRef | null;
  comment_id?: string | null;
  review_request_id?: string | null;
}

export interface NotificationListResponse {
  items: NotificationItem[];
  total: number;
}

export interface NotificationUnreadCount {
  count: number;
}

// --- Step 11: Admin ---

export interface AdminUserPublic {
  id: string;
  email: string;
  name: string;
  status: UserStatus;
  system_role: SystemRole;
  must_change_password: boolean;
  failed_login_count: number;
  locked_until: string | null;
  temporary_login_locked: boolean;
  active_session_count: number;
  last_seen_at: string | null;
  created_at: string;
  updated_at: string;
  is_current_user: boolean;
}

export interface AdminUserListResponse {
  items: AdminUserPublic[];
  total: number;
}

export interface AdminUserCreateRequest {
  email: string;
  name: string;
  temporary_password: string;
  system_role?: SystemRole;
}

export interface AdminUserUpdateRequest {
  name?: string;
  status?: UserStatus;
  system_role?: SystemRole;
}

export interface AdminPasswordResetRequest {
  temporary_password: string;
}

export interface SettingMetadata {
  source: string;
  updated_at: string | null;
  updated_by: { id: string; name: string } | null;
}

export interface SystemSettingsResponse {
  global_llm_enabled: boolean;
  global_web_search_enabled: boolean;
  default_team_allow_llm: boolean;
  default_team_allow_web_search: boolean;
  metadata: Record<string, SettingMetadata>;
}

export interface SystemSettingsUpdateRequest {
  global_llm_enabled?: boolean;
  default_team_allow_llm?: boolean;
  global_web_search_enabled?: boolean;
  default_team_allow_web_search?: boolean;
}

export interface LlmIntegrationConfig {
  provider: string;
  api_url: string;
  chat_completions_path: string;
  model_name: string;
  api_key_configured: boolean;
  timeout_seconds: number;
  connect_timeout_seconds: number;
  max_tokens: number;
  temperature: number;
  enable_thinking: boolean | null;
  configuration_source: string;
}

export interface WebSearchIntegrationConfig {
  provider: string;
  api_url: string | null;
  api_key_configured: boolean;
  timeout_seconds: number;
  connect_timeout_seconds: number;
  max_queries: number;
  max_results_per_query: number;
  max_total_results: number;
  configured: boolean;
  configuration_source: string;
}

export interface AdminIntegrationConfigResponse {
  llm: LlmIntegrationConfig;
  web_search: WebSearchIntegrationConfig;
  global_llm_enabled: boolean;
  global_web_search_enabled: boolean;
}

export interface LlmConnectionTestResult {
  status: string;
  provider?: string | null;
  model?: string | null;
  latency_ms?: number | null;
  tested_at: string;
  error_code?: string | null;
  retryable?: boolean | null;
  safe_message?: string | null;
}

export interface WebSearchTestResultItem {
  title: string;
  url: string;
  source?: string | null;
  published_at?: string | null;
}

export interface WebSearchConnectionTestResult {
  status: string;
  provider?: string | null;
  latency_ms?: number | null;
  result_count?: number | null;
  tested_at: string;
  error_code?: string | null;
  retryable?: boolean | null;
  safe_message?: string | null;
  results?: WebSearchTestResultItem[] | null;
}

/* --- Step 14: Idea Validation --- */

export type IdeaValidationStatus =
  | "DRAFT"
  | "READY"
  | "RUNNING"
  | "COMPLETED"
  | "CANCELLED";

export type IdeaValidationOutcome =
  | "PASS"
  | "PARTIAL"
  | "FAIL"
  | "INCONCLUSIVE";

export interface IdeaValidation {
  id: string;
  idea_id: string;
  title: string;
  hypothesis: string;
  method: string;
  success_criteria: string;
  planned_evidence: string | null;
  status: IdeaValidationStatus;
  outcome: IdeaValidationOutcome | null;
  result_summary: string | null;
  evidence_summary: string | null;
  due_date: string | null;
  started_at: string | null;
  completed_at: string | null;
  created_by: IdeaUserRef;
  created_at: string;
  updated_at: string;
}

export interface IdeaValidationListResponse {
  items: IdeaValidation[];
  total: number;
}

export interface IdeaValidationCreateRequest {
  title: string;
  hypothesis: string;
  method: string;
  success_criteria: string;
  planned_evidence?: string | null;
  due_date?: string | null;
}

export type IdeaValidationUpdateRequest = Partial<IdeaValidationCreateRequest>;

export interface IdeaValidationCompleteRequest {
  outcome: IdeaValidationOutcome;
  result_summary: string;
  evidence_summary?: string | null;
}

export interface IdeaValidationStartResponse {
  validation: IdeaValidation;
  idea_stage: StageRef;
}
