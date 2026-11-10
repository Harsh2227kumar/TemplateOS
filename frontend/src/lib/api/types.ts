// Request and response shapes shared by the API modules. Types only.

// --- Auth ---

export interface UserPreferences {
  default_document_format: string | null;
  email_notifications: boolean | null;
}

export interface User {
  id: number;
  email: string;
  full_name: string;
  role: string;
  organization_id: number | null;
  institute_id?: number | null;
  department_id: number | null;
  /** Names of the linked organization / institute / department (read-only for the user). */
  department: string | null;
  institute?: string | null;
  organization: string | null;
  /** EkLink identity (PRN / staff ID); null for local accounts. */
  login_id?: string | null;
  member_type?: string | null;
  batch?: string | null;
  section?: string | null;
  semester?: number | null;
  job_title: string | null;
  phone: string | null;
  avatar_url: string | null;
  signature_path: string | null;
  preferences: UserPreferences | null;
  is_demo?: boolean;
  /** Linked to EkLink: name, email, placement and member type come from there. */
  managed_by_eklink?: boolean;
}

/** PATCH /auth/me: the only fields a user may change on themselves. */
export interface ProfileUpdate {
  full_name?: string;
  phone?: string | null;
  job_title?: string | null;
}

/** Body of POST /auth/login. The session itself travels in httpOnly cookies. */
export interface TokenResponse {
  access_token: string;
  token_type: string;
}

/** GET /auth/eklink: whether "Sign in with EkLink" is available. */
export interface EklinkConfig {
  enabled: boolean;
  eklink_url: string | null;
  /** Whether the login page should offer "Create an account". */
  signup_enabled?: boolean;
}

export interface TemplateListItem extends TemplateAudience {
  id: number;
  name: string;
  category: string;
  visibility: string;
  status: string;
  uploaded_by: number;
  created_at: string;
}

export interface TemplateLibraryResponse {
  templates: TemplateListItem[];
  total: number;
  page: number;
  limit: number;
}

export interface TemplateResponse extends TemplateAudience {
  id: number;
  name: string;
  description: string | null;
  category: string;
  visibility: string;
  status: string;
  original_file_path: string | null;
  original_filename: string | null;
  file_size_bytes: number | null;
  uploaded_by: number;
  version: number;
  created_at: string;
  updated_at: string;
  processed_file_path?: string | null;
}

// --- Template audience: organization / department scope + role restriction ---

export type TemplateVisibility =
  | "private"
  | "public"
  | "organization"
  | "institute"
  | "department"
  | "group";

export interface TemplateAudience {
  scope_organization_id: number | null;
  scope_institute_id?: number | null;
  scope_department_id: number | null;
  scope_institute?: string | null;
  /** Display names of the linked organization / department rows. */
  scope_organization: string | null;
  scope_department: string | null;
  /** null = every role in scope */
  allowed_roles: string[] | null;
  /** Computed by the server for the current user. */
  can_manage: boolean;
  /** V1.7 P2.1: set on a personal copy ("Customize for me") of another template. */
  parent_template_id: number | null;
  parent_template_name: string | null;
  is_personal_copy: boolean;
}

export interface TemplateAccessUpdate {
  visibility: TemplateVisibility;
  scope_organization_id?: number | null;
  scope_institute_id?: number | null;
  scope_department_id?: number | null;
  allowed_roles?: string[] | null;
}

export interface OrganizationOption {
  id: number;
  name: string;
}

export interface InstituteOption {
  id: number;
  organization_id: number;
  name: string;
}

export interface DepartmentOption {
  id: number;
  organization_id: number;
  institute_id?: number | null;
  name: string;
}

export interface TemplateAccessOptions {
  roles: { value: string; label: string }[];
  organizations: OrganizationOption[];
  institutes?: InstituteOption[];
  departments: DepartmentOption[];
  can_publish: { organization: boolean; department: boolean; institute?: boolean };
  defaults: {
    organization_id: number | null;
    department_id: number | null;
    institute_id?: number | null;
  };
}

// --- Administration: users, organizations, departments ---

export interface AdminUser {
  id: number;
  email: string;
  full_name: string;
  role: string;
  organization_id: number | null;
  organization: string | null;
  institute_id?: number | null;
  institute?: string | null;
  department_id: number | null;
  department: string | null;
  job_title: string | null;
  phone: string | null;
  login_id?: string | null;
  member_type?: string | null;
  is_active?: boolean;
  batch?: string | null;
  section?: string | null;
  semester?: number | null;
  /** Signs in through EkLink (no local password). */
  sso?: boolean;
  is_demo?: boolean;
  /** Linked to EkLink: placement, member type and the active flag are read-only here. */
  managed_by_eklink?: boolean;
}

export interface AdminUserList {
  users: AdminUser[];
  total: number;
  page: number;
  limit: number;
}

export interface AdminUserListParams {
  search?: string;
  role?: string;
  organization_id?: number;
  institute_id?: number;
  department_id?: number;
  member_type?: string;
  is_active?: boolean;
  page?: number;
  limit?: number;
}

/** PATCH /admin/users/{id}: only the keys present are applied; null clears. */
export interface AdminUserUpdate {
  role?: string;
  organization_id?: number | null;
  institute_id?: number | null;
  department_id?: number | null;
  member_type?: string | null;
  is_active?: boolean;
}

export interface Organization {
  id: number;
  name: string;
  code?: string | null;
  is_active?: boolean;
  is_demo?: boolean;
  /** Has a code: mirrored from EkLink, read-only here. */
  managed_by_eklink?: boolean;
  created_at: string;
  institute_count?: number;
  department_count: number;
  user_count: number;
}

export interface Institute {
  id: number;
  organization_id: number;
  name: string;
  code: string | null;
  is_active: boolean;
  is_demo?: boolean;
  managed_by_eklink?: boolean;
  created_at: string;
  department_count: number;
  user_count: number;
}

export interface Department {
  id: number;
  organization_id: number;
  institute_id?: number | null;
  name: string;
  code?: string | null;
  is_active?: boolean;
  is_demo?: boolean;
  managed_by_eklink?: boolean;
  created_at: string;
  user_count: number;
}

/** Name / code / active edits for organizations, institutes and departments. */
export interface DirectoryUpdate {
  name?: string;
  code?: string | null;
  is_active?: boolean;
}

export type ApproverScopeLevel = "organization" | "institute" | "department";

export interface ApproverAssignment {
  id: number;
  user_id: number;
  user_name: string | null;
  user_email: string | null;
  user_login_id: string | null;
  title: string;
  scope_level: ApproverScopeLevel;
  organization_id: number;
  institute_id: number | null;
  department_id: number | null;
  scope_name: string | null;
  scope_key: string | null;
  valid_from: string;
  valid_to: string | null;
  is_current: boolean;
  created_at: string;
  /** "eklink": mirrored from EkLink (ended there); "local": made in TemplateOS. */
  source?: "local" | "eklink";
  eklink_id?: string | null;
  managed_by_eklink?: boolean;
}

export interface ApproverAssignmentList {
  assignments: ApproverAssignment[];
  total: number;
  titles: string[];
  /** False while EkLink sync is on (approvers are assigned in EkLink). */
  can_create?: boolean;
}

// --- EkLink sync ---

export interface SyncLinks {
  admin: string | null;
  users: string | null;
  directory: string | null;
  approvers: string | null;
}

/** GET /admin/sync/status (any admin). */
export interface SyncStatus {
  /** Sync configured and on: EkLink-owned data is read-only. */
  enabled: boolean;
  configured: boolean;
  eklink_url: string | null;
  eklink_admin_url: string | null;
  links: SyncLinks;
  interval_minutes: number;
  full_at: string;
  /** The caller may run "Sync now" / "Full resync" (super admin). */
  can_run: boolean;
  last_event_id: number;
  last_pull_at: string | null;
  last_push_at: string | null;
  last_full_sync_at: string | null;
  last_error: string | null;
  last_error_at: string | null;
  last_result: Record<string, unknown> | null;
  pending_count: number;
}

/** POST /admin/sync/run and /admin/sync/full. */
export interface SyncRunResult {
  last_event_id: number;
  result: Record<string, unknown> | null;
  status: SyncStatus;
}

export interface ApproverAssignmentCreate {
  user_id: number;
  title: string;
  scope_level: ApproverScopeLevel;
  organization_id?: number | null;
  institute_id?: number | null;
  department_id?: number | null;
  scope_key?: string | null;
  valid_from?: string | null;
  valid_to?: string | null;
}


export interface TemplateField {
  id: number;
  template_id: number;
  field_name: string;
  field_label: string | null;
  field_type: string;
  default_value: string | null;
  is_required: boolean;
  description: string | null;
  example_value: string | null;
  validation_rule: string | null;
  section: string | null;
  ai_enabled: boolean;
  display_order: number;
  /** Provenance: detected | cleaned | manual | ai. */
  source?: string;
  created_at: string;
  updated_at: string;
}

export interface DetectionWarnings {
  duplicates: { key: string; count: number }[];
  invalid_names: { raw: string; suggested_key: string; count: number; reason: string }[];
  parse_error: string | null;
}

export interface PlaceholderDetectionResponse {
  template_id: number;
  status: string;
  already_detected: boolean;
  detected_fields: TemplateField[];
  warnings: DetectionWarnings;
  summary: {
    total_matches: number;
    unique_valid: number;
    invalid_count: number;
    duplicate_count: number;
  };
  /** "processed" when the cleaned copy was scanned. */
  source_file?: "original" | "processed";
  /** Keys created by this run (non-force re-runs only add new keys). */
  added_fields?: string[];
  /** Fields whose placeholder is no longer in the scanned document. */
  stale_fields?: string[];
}

export interface PlaceholderFix {
  raw: string;
  key: string;
}

// --- V1.3 Phase 3: field metadata editor ---

export interface TemplateFieldUpsert {
  id?: number;
  field_name: string;
  field_label?: string;
  field_type?: string;
  default_value?: string;
  is_required: boolean;
  description?: string;
  example_value?: string;
  validation_rule?: string;
  section?: string;
  ai_enabled: boolean;
}

export interface FieldSyncPayload {
  fields: TemplateFieldUpsert[];
  mark_configured?: boolean;
}

// --- V1.3 Phase 2: manual template cleaning ---

export interface DocSegment {
  index: number;
  location: "body" | "table" | "header" | "footer" | "textbox";
  text: string;
}

export interface TemplateContent {
  template_id: number;
  segments: DocSegment[];
  has_processed: boolean;
  source?: "original" | "processed";
}

/** Exact spot in the ORIGINAL document (from /clean-suggestions). */
export interface CleanAnchor {
  paragraph_id: number;
  start: number;
  end: number;
  action: "replace" | "insert" | "list";
  paragraph_ids?: number[];
}

export interface PlaceholderReplacement {
  /** Text to replace; may be empty for an anchored insert. */
  sample_text: string;
  placeholder_key: string;
  field_label?: string;
  field_type?: string;
  section?: string;
  segment_index?: number;
  anchor?: CleanAnchor;
  example_value?: string;
  validation_rule?: string;
  is_required?: boolean;
  ai_enabled?: boolean;
}

export type SuggestionGroup =
  | "fixes"
  | "lists"
  | "tables"
  | "blanks"
  | "brackets"
  | "empty_values"
  | "filled_values"
  | "detected_values";

export interface CleanSuggestion {
  id: string;
  kind: string;
  group: SuggestionGroup;
  placeholder_key: string;
  field_label: string;
  field_type: string;
  validation_rule: string | null;
  is_required: boolean;
  ai_enabled: boolean;
  section: string | null;
  example_value: string | null;
  confidence: number;
  high_confidence: boolean;
  reason: string;
  sample_text: string;
  location: DocSegment["location"];
  shared_key_count: number;
  anchor: CleanAnchor;
  context: { before: string; match: string; after: string; paragraph_text: string };
}

export interface CleanSuggestionsResponse {
  template_id: number;
  source: "original";
  has_processed: boolean;
  suggestion_count: number;
  high_confidence_count: number;
  high_confidence_threshold: number;
  existing_placeholders: string[];
  suggestions: CleanSuggestion[];
}

export interface ReplacementResult {
  placeholder_key: string;
  sample_text: string;
  occurrences: number;
  matched: boolean;
  reason?: string | null;
}

export interface CleanResponse {
  template_id: number;
  status: string;
  processed_file_path: string;
  created_fields: TemplateField[];
  results: ReplacementResult[];
  warnings: CleanWarnings;
  detected_keys?: string[];
}

export interface CleanWarnings {
  unmatched: string[];
  invalid_keys: string[];
  stale_fields?: string[];
  render_error?: string | null;
}

export interface CleanPreviewResponse {
  template_id: number;
  segments: DocSegment[];
  results: ReplacementResult[];
  warnings: CleanWarnings;
  detected_keys: string[];
}

export interface CleanTemplatePayload {
  replacements: PlaceholderReplacement[];
  confirm: boolean;
  mark_configured?: boolean;
}

// --- V1.3 Phase 4: AI field suggestions (proposals only — nothing persists here) ---

export interface FieldSuggestion {
  field_name: string;
  field_label: string | null;
  field_type: string;
  section: string | null;
  is_required: boolean;
  example_value: string | null;
  reason: string | null;
}

export interface SuggestFieldsResponse {
  template_id: number;
  model: string;
  existing_count: number;
  suggestion_count: number;
  suggestions: FieldSuggestion[];
}

// --- V1.4 Phase 2: Document Drafts ---

// V1.7 Phase 2: textarea values may be rich text (Tiptap JSON, whitelisted
// by the backend: paragraphs, hard breaks, bullet / numbered lists; bold,
// italic, underline, strike, highlight, http(s) / mailto links).
export interface RichTextNode {
  type: string;
  text?: string;
  marks?: Array<{ type: string; attrs?: Record<string, unknown> }>;
  attrs?: Record<string, unknown>;
  content?: RichTextNode[];
}

export interface RichTextDoc extends RichTextNode {
  type: "doc";
  content: RichTextNode[];
}

export type ValueFormat = "plain" | "rich";

export interface DocumentValue {
  id: number;
  document_id: number;
  field_name: string;
  /** Plain text; for rich values the server-derived plain projection. */
  value: string;
  created_at: string;
  updated_at: string;
  /** V1.7 P2 */
  value_format: ValueFormat;
  rich_content: RichTextDoc | null;
  /** The saved value is an AI result the user did not edit afterwards. */
  ai_modified: boolean;
  ai_action: AiTextAction | null;
  ai_modified_at: string | null;
}

export interface Document {
  id: number;
  template_id: number;
  created_by: number;
  name: string | null;
  status: string;
  created_at: string;
  updated_at: string;
  template_name?: string;
  values?: DocumentValue[];
  /** V1.6: latest generated output; null until the first generation. */
  generated?: GeneratedInfo | null;
}

// --- V1.6: Document generation ---

/** pending: conversion did not finish · converted · failed (see pdf_error). */
export type PdfStatus = "pending" | "converted" | "failed";

export interface GeneratedInfo {
  /** V1.7 P2: the version number of this (latest) output. */
  version: number | null;
  generated_at: string;
  pdf_status: PdfStatus;
  /** User-readable reason of the last failed conversion. */
  pdf_error: string | null;
  /** Stored PDF file name (no path); null without a PDF. */
  pdf_filename: string | null;
  pdf_converted_at: string | null;
  /** Conversions tried for the current DOCX (initial + retries). */
  pdf_attempts: number;
  /** A PDF file exists; can be true while pdf_status is "failed" (an earlier PDF). */
  has_pdf: boolean;
  /** API path (with the /api/v1 prefix) of the DOCX download. */
  docx_url: string;
  /** API path of the PDF download (/download/pdf); null without a PDF. */
  pdf_url: string | null;
  /** The draft's values were saved after this generation. */
  is_stale: boolean;
  template_version: number | null;
}

export interface GenerateDocumentResponse extends GeneratedInfo {
  document_id: number;
  document_status: string;
  /** V1.7 P2: every generate creates a version; how many exist now. */
  versions_count: number;
}

// --- V1.7 Phase 1: read-only document preview (GET /documents/{id}/preview) ---

export interface PreviewDocumentInfo {
  id: number;
  name: string | null;
  status: string;
  created_at: string;
  updated_at: string;
}

export interface PreviewTemplateInfo {
  id: number;
  name: string;
  category: string;
  version: number;
  has_processed_file: boolean;
}

export interface PreviewCompleteness {
  required_total: number;
  required_filled: number;
  /** Field names (not labels) of required fields without a value. */
  missing_required: string[];
}

export interface PreviewField {
  field_name: string;
  label: string;
  field_type: string;
  is_required: boolean;
  ai_enabled: boolean;
  display_order: number;
  /** Raw saved value; null when never saved. */
  value: string | null;
  /** Exactly as generation renders it (e.g. ISO date -> DD-MM-YYYY). */
  display_value: string;
  /** List fields only. */
  items: string[] | null;
  is_empty: boolean;
  missing_required: boolean;
  /** V1.7 P2: rich textarea values carry their Tiptap JSON. */
  value_format: ValueFormat;
  rich_content: RichTextDoc | null;
  ai_modified: boolean;
  ai_action: AiTextAction | null;
}

export interface PreviewSection {
  /** A field without a section is grouped under "General" by the API. */
  name: string;
  fields: PreviewField[];
}

export interface PreviewGeneration {
  generated_at: string;
  is_stale: boolean;
  template_version: number | null;
  /** The generated DOCX exists on disk. */
  docx_available: boolean;
  docx_url: string;
  pdf_status: PdfStatus;
  pdf_error: string | null;
  /** A PDF file exists on disk. */
  pdf_available: boolean;
  pdf_url: string | null;
  pdf_filename: string | null;
  /** V1.7 P2: the latest version's number and how many versions exist. */
  version: number | null;
  versions_count: number;
  /** V1.7 P2.1: "manual_edit" when the latest version was edited in the Word editor. */
  source: string;
}

export interface PreviewPermissions {
  can_edit: boolean;
  can_generate: boolean;
  can_download: boolean;
}

export interface DocumentPreview {
  document: PreviewDocumentInfo;
  template: PreviewTemplateInfo;
  completeness: PreviewCompleteness;
  sections: PreviewSection[];
  /** null when the draft was never generated. */
  generation: PreviewGeneration | null;
  permissions: PreviewPermissions;
}

export type DocumentFormValues = Record<string, any>;

export interface DocumentCreate {
  template_id: number;
  name?: string;
}

/** One value in PUT /documents/{id}/values (plain-only items stay valid). */
export interface DocumentValueSaveItem {
  field_name: string;
  /** Ignored by the server for rich values (derived from rich_content). */
  value: string;
  value_format?: ValueFormat;
  rich_content?: RichTextDoc | null;
  ai_modified?: boolean;
  ai_action?: AiTextAction | null;
}

export interface DocumentValuesSave {
  values: DocumentValueSaveItem[];
}

export interface DocumentValuesResponse {
  document_id: number;
  values: DocumentValue[];
}

// --- V1.7 Phase 2: document versions (GET /documents/{id}/versions) ---

/** V1.7 P2.1: "manual_edit" = the Word file was edited by hand (values unchanged). */
export type VersionSource = "generated" | "manual_edit";

export interface DocumentVersion {
  version: number;
  source: VersionSource;
  /** The version a manual edit started from; null for generated versions. */
  base_version: number | null;
  created_at: string;
  /** "Deleted user" when the account is gone. */
  created_by_name: string;
  template_version: number | null;
  pdf_status: PdfStatus | null;
  pdf_error: string | null;
  /** The file can be downloaded (false once pruned or missing). */
  has_docx: boolean;
  has_pdf: boolean;
  /** Retention removed this version's files; its values stay viewable. */
  files_pruned: boolean;
  /** field_names changed since the previous version ([] for version 1). */
  changed_fields: string[];
  is_latest: boolean;
  docx_url: string | null;
  pdf_url: string | null;
}

export interface DocumentVersionDetail extends DocumentVersion {
  document_id: number;
  /** The version's values (from its snapshot), shaped like the preview. */
  sections: PreviewSection[];
}

// --- V1.5 Phase 1: basic AI writing actions on a single field ---

export type AiTextAction = "grammar" | "tone" | "concise" | "formal" | "expand";

/**
 * Text fields send original_text; list fields send original_items (one
 * entry per item, rewritten one by one); rich paragraph (textarea) fields
 * send their non-empty paragraphs and list items as original_items.
 */
export interface ImproveTextRequest {
  template_id: number;
  document_id?: number | null;
  field_name: string;
  original_text?: string;
  original_items?: string[];
  action_type: AiTextAction;
}

export interface ImproveTextResponse {
  improved_text: string;
  /** When original_items were sent: the rewritten items, same count and order. */
  improved_items?: string[];
}


// --- V1.7 Phase 2.1: Word file editor (ONLYOFFICE Docs) ---

export type EditorTarget = "template" | "document";
export type EditorSessionStatus = "open" | "saving" | "saved" | "closed" | "failed" | "expired";
export type RevisionSource = "upload" | "clean" | "fix_placeholders" | "customize" | "manual_edit" | "restore";

/** GET /system/editor-config */
export interface EditorStatusConfig {
  enabled: boolean;
  document_server_url: string | null;
}

/** POST .../editor-session: `config` is signed; pass it to DocsAPI.DocEditor unchanged. */
export interface EditorConfigResponse {
  session_key: string;
  document_server_url: string;
  config: Record<string, any>;
  /** The user's open session for the same file was reused. */
  reused: boolean;
}

/** GET /editor/sessions/{key} */
export interface EditorSessionRead {
  session_key: string;
  status: EditorSessionStatus;
  target_type: EditorTarget;
  template_id: number | null;
  document_id: number | null;
  /** Template revision / document version created by the save. */
  result_revision: number | null;
  result_version: number | null;
  error: string | null;
  created_at: string;
  updated_at: string;
  expires_at: string;
}

/** GET /templates/{id}/revisions (newest first) */
export interface TemplateRevision {
  revision: number;
  source: RevisionSource;
  created_at: string;
  created_by_name: string;
  placeholders_added: string[];
  placeholders_removed: string[];
  blank_suggestions: number;
  note: string | null;
  is_current: boolean;
}

export interface AddedPlaceholder {
  key: string;
  suggested_label: string;
  suggested_type: string;
}

/** GET /templates/{id}/field-changes: what the current file means for the form. */
export interface FieldChanges {
  template_id: number;
  revision: number;
  added: AddedPlaceholder[];
  /** Configured field names no longer in the file. */
  removed: string[];
  /** Blanks ("______", empty values, [brackets]) that can become fields. */
  blank_suggestions: number;
  renderable: boolean;
  render_error: string | null;
  has_changes: boolean;
}

// --- V1.7 Phase 3: download history and audit log ---

export interface Paginated<T> {
  items: T[];
  total: number;
  page: number;
  limit: number;
}

/** GET /me/downloads, GET /documents/{id}/downloads */
export interface DownloadHistoryItem {
  id: number;
  downloaded_at: string;
  format: "docx" | "pdf";
  /** null once the document was deleted (document_name is a snapshot). */
  document_id: number | null;
  document_name: string;
  version: number | null;
  /** "generated" | "manual_edit" (P2.1) */
  version_source: string | null;
  file_name: string;
  file_size: number | null;
  document_exists: boolean;
}

export interface DownloadHistoryParams {
  page?: number;
  limit?: number;
  format?: "docx" | "pdf";
  document_id?: number;
}

/** GET /admin/audit-logs */
export interface AuditLogItem {
  id: number;
  created_at: string;
  /** null: the account was deleted, or no actor (failed login). */
  actor_id: number | null;
  actor_email: string | null;
  action: string;
  entity_type: string;
  entity_id: number | null;
  summary: string;
  details: Record<string, unknown> | null;
  ip_address: string | null;
}

/** GET /admin/audit-logs/actions */
export interface AuditActionOption {
  action: string;
  label: string;
  area: string;
}

/** Query of GET /admin/audit-logs and /export.csv (dates YYYY-MM-DD, UTC days, "to" inclusive). */
export interface AuditLogParams {
  page?: number;
  limit?: number;
  action?: string;
  actor_id?: number;
  entity_type?: string;
  entity_id?: number;
  from?: string;
  to?: string;
  q?: string;
}
