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
  department: string | null;
  organization: string | null;
  job_title: string | null;
  phone: string | null;
  avatar_url: string | null;
  signature_path: string | null;
  preferences: UserPreferences | null;
}

/** Body of POST /auth/login. The session itself travels in httpOnly cookies. */
export interface TokenResponse {
  access_token: string;
  token_type: string;
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
  original_file_path: string;
  original_filename: string | null;
  file_size_bytes: number | null;
  uploaded_by: number;
  version: number;
  created_at: string;
  updated_at: string;
  processed_file_path?: string | null;
}

// --- Template audience: organization / department scope + role restriction ---

export type TemplateVisibility = "private" | "public" | "organization" | "department" | "group";

export interface TemplateAudience {
  scope_organization: string | null;
  scope_department: string | null;
  /** null = every role in scope */
  allowed_roles: string[] | null;
  /** Computed by the server for the current user. */
  can_manage: boolean;
}

export interface TemplateAccessUpdate {
  visibility: TemplateVisibility;
  scope_organization?: string | null;
  scope_department?: string | null;
  allowed_roles?: string[] | null;
}

export interface TemplateAccessOptions {
  roles: { value: string; label: string }[];
  organizations: string[];
  departments: { organization: string | null; department: string }[];
  can_publish: { organization: boolean; department: boolean };
  defaults: { organization: string | null; department: string | null };
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

export interface DocumentValue {
  id: number;
  document_id: number;
  field_name: string;
  value: string;
  created_at: string;
  updated_at: string;
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

export type PdfStatus = "ok" | "failed" | "not_configured";

export interface GeneratedInfo {
  generated_at: string;
  pdf_status: PdfStatus;
  pdf_error: string | null;
  /** API path (with the /api/v1 prefix) of the DOCX download. */
  docx_url: string;
  pdf_url: string | null;
  /** The draft's values were saved after this generation. */
  is_stale: boolean;
  template_version: number | null;
}

export interface GenerateDocumentResponse extends GeneratedInfo {
  document_id: number;
  document_status: string;
}

export type DocumentFormValues = Record<string, any>;

export interface DocumentCreate {
  template_id: number;
  name?: string;
}

export interface DocumentValuesSave {
  values: Array<{ field_name: string; value: string }>;
}

export interface DocumentValuesResponse {
  document_id: number;
  values: DocumentValue[];
}

// --- V1.5 Phase 1: basic AI writing actions on a single field ---

export type AiTextAction = "grammar" | "tone" | "concise" | "formal";

export interface ImproveTextRequest {
  template_id: number;
  document_id?: number | null;
  field_name: string;
  original_text: string;
  action_type: AiTextAction;
}

export interface ImproveTextResponse {
  improved_text: string;
}

