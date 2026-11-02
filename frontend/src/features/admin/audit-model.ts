/**
 * Pure helpers for the admin Audit log page (V1.7 Phase 3): filters <-> URL
 * query (shareable links), date range rules (same as the server), action
 * grouping, labels and entity links. Type imports only (`node --test`).
 */
import type { AuditActionOption, AuditLogItem, AuditLogParams } from "../../lib/api/types";

export const MAX_RANGE_DAYS = 366;
export const DEFAULT_RANGE_DAYS = 30;
export const AUDIT_PAGE_SIZE = 25;

export interface AuditFilters {
  action: string;
  entityType: string;
  /** YYYY-MM-DD (UTC days; `to` inclusive). */
  from: string;
  to: string;
  q: string;
  page: number;
}

const AREA_LABELS: Record<string, string> = {
  templates: "Templates",
  documents: "Documents",
  editor: "Editor",
  ai: "AI",
  admin: "Admin",
  auth: "Sign-in",
};

export const ENTITY_TYPE_OPTIONS: { value: string; label: string }[] = [
  { value: "template", label: "Template" },
  { value: "document", label: "Document" },
  { value: "user", label: "User" },
  { value: "organization", label: "Organization" },
  { value: "department", label: "Department" },
  { value: "audit_log", label: "Audit log" },
];

/** YYYY-MM-DD of a Date in UTC. */
export function isoDay(date: Date): string {
  return date.toISOString().slice(0, 10);
}

/** The last 30 days, ending today. */
export function defaultFilters(today: Date = new Date()): AuditFilters {
  const from = new Date(today.getTime() - (DEFAULT_RANGE_DAYS - 1) * 86_400_000);
  return { action: "", entityType: "", from: isoDay(from), to: isoDay(today), q: "", page: 1 };
}

const DAY = /^\d{4}-\d{2}-\d{2}$/;

/** Filters from a URL query; anything missing or malformed falls back to the defaults. */
export function queryToAuditFilters(search: string | URLSearchParams, today: Date = new Date()): AuditFilters {
  const params = typeof search === "string" ? new URLSearchParams(search) : search;
  const base = defaultFilters(today);
  const page = Number(params.get("page"));
  const day = (key: string, fallback: string) => {
    const value = params.get(key);
    if (value === "") return "";
    return value && DAY.test(value) ? value : fallback;
  };
  return {
    action: params.get("action") ?? "",
    entityType: params.get("entity_type") ?? "",
    from: day("from", base.from),
    to: day("to", base.to),
    q: params.get("q") ?? "",
    page: Number.isInteger(page) && page > 0 ? page : 1,
  };
}

/** URL query for the filters (dates always kept so the link is reproducible). */
export function auditFiltersToQuery(filters: AuditFilters): string {
  const params = new URLSearchParams();
  if (filters.action) params.set("action", filters.action);
  if (filters.entityType) params.set("entity_type", filters.entityType);
  params.set("from", filters.from);
  params.set("to", filters.to);
  if (filters.q.trim()) params.set("q", filters.q.trim());
  if (filters.page > 1) params.set("page", String(filters.page));
  return params.toString();
}

/** API params for GET /admin/audit-logs. */
export function auditFiltersToParams(filters: AuditFilters, limit: number = AUDIT_PAGE_SIZE): AuditLogParams {
  return {
    page: filters.page,
    limit,
    action: filters.action || undefined,
    entity_type: filters.entityType || undefined,
    from: filters.from || undefined,
    to: filters.to || undefined,
    q: filters.q.trim() || undefined,
  };
}

/** Why a date range is not allowed (null when it is): from <= to, at most 366 days. */
export function dateRangeError(from: string, to: string): string | null {
  if (!from || !to) return null;
  const start = Date.parse(`${from}T00:00:00Z`);
  const end = Date.parse(`${to}T00:00:00Z`);
  if (Number.isNaN(start) || Number.isNaN(end)) return "Enter valid dates.";
  if (start > end) return "The start date must be on or before the end date.";
  if ((end - start) / 86_400_000 + 1 > MAX_RANGE_DAYS) return `Pick at most ${MAX_RANGE_DAYS} days.`;
  return null;
}

export interface ActionGroup {
  area: string;
  label: string;
  actions: AuditActionOption[];
}

/** Catalog actions grouped by area, in catalog order. */
export function groupActions(options: AuditActionOption[]): ActionGroup[] {
  const groups = new Map<string, ActionGroup>();
  for (const option of options) {
    const group = groups.get(option.area) ?? { area: option.area, label: AREA_LABELS[option.area] ?? option.area, actions: [] };
    group.actions.push(option);
    groups.set(option.area, group);
  }
  return [...groups.values()];
}

/** The label of an action, falling back to the raw action. */
export function actionLabel(action: string, options: AuditActionOption[] | undefined): string {
  return options?.find((option) => option.action === action)?.label ?? action;
}

/**
 * Who did it: the email (kept after the account is deleted; for a failed
 * login, the email that was tried), else "System".
 */
export function actorLabel(item: Pick<AuditLogItem, "actor_id" | "actor_email">): string {
  if (item.actor_email) return item.actor_email;
  return item.actor_id === null ? "System" : `User #${item.actor_id}`;
}

/** In-app link of the row's entity, or null. */
export function entityLink(item: Pick<AuditLogItem, "entity_type" | "entity_id">): string | null {
  if (item.entity_id === null) return null;
  switch (item.entity_type) {
    case "template":
    case "template_revision":
      return `/templates/${item.entity_id}`;
    case "document":
    case "document_version":
      return `/documents/${item.entity_id}/preview`;
    case "organization":
    case "department":
      return "/admin/organizations";
    default:
      return null;
  }
}

/** "Template #12" */
export function entityText(item: Pick<AuditLogItem, "entity_type" | "entity_id">): string {
  const label = ENTITY_TYPE_OPTIONS.find((option) => option.value === item.entity_type)?.label
    ?? item.entity_type.replace(/_/g, " ");
  return item.entity_id === null ? label : `${label} #${item.entity_id}`;
}
