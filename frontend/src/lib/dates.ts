/**
 * The API returns naive UTC timestamps such as "2026-10-13T10:21:05" (no "Z").
 * `new Date()` reads those as local time, so in India every "x ago" label was
 * about 5.5 hours off. Treat a timestamp without a zone as UTC.
 */
const HAS_ZONE = /(?:[zZ]|[+-]\d{2}:?\d{2})$/;
const HAS_TIME = /\d{2}:\d{2}/;

export function parseServerDate(value: string | null | undefined): Date | null {
  if (!value) return null;
  const trimmed = value.trim();
  const iso =
    HAS_TIME.test(trimmed) && !HAS_ZONE.test(trimmed)
      ? `${trimmed.replace(" ", "T")}Z`
      : trimmed;
  const date = new Date(iso);
  return Number.isNaN(date.getTime()) ? null : date;
}

/** Milliseconds since epoch for sorting; 0 when the value is missing or invalid. */
export function serverTime(value: string | null | undefined): number {
  return parseServerDate(value)?.getTime() ?? 0;
}
