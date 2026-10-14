/**
 * Splits a list field's example value into one placeholder per item.
 *
 * Examples for list fields are stored like list values: a JSON array of
 * strings (e.g. '["Budget approval", "Venue selection"]'). Shown as-is, the
 * raw JSON looks like text already typed into the first input. Non-JSON text
 * is treated as a single example item; blank items are dropped.
 */
export function listExampleItems(example: string | null | undefined): string[] {
  const text = example?.trim();
  if (!text) return [];
  if (text.startsWith("[")) {
    try {
      const parsed: unknown = JSON.parse(text);
      if (Array.isArray(parsed)) {
        return parsed
          .filter((item): item is string | number => typeof item === "string" || typeof item === "number")
          .map((item) => String(item).trim())
          .filter((item) => item.length > 0);
      }
    } catch {
      // Not valid JSON: fall through and use the text as one item.
    }
  }
  return [text];
}
