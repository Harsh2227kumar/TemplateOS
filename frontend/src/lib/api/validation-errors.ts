
/**
 * Splits a 422 `detail` payload into errors that belong to rendered form fields
 * and messages that cannot be mapped to one. Supports both the app validator
 * format (`{field_name, error}`) and FastAPI/Pydantic request validation
 * (`{loc, msg, type}`). Returns null when `detail` is not an array.
 */
export function splitValidationErrors(
  detail: unknown,
  fieldNames: string[],
): { fieldErrors: Record<string, string>; otherMessages: string[] } | null {
  if (!Array.isArray(detail)) return null;
  const known = new Set(fieldNames);
  const fieldErrors: Record<string, string> = {};
  const otherMessages: string[] = [];

  for (const item of detail) {
    let name: string | undefined;
    let message: string | undefined;
    let location: string | undefined;

    if (item && typeof item === "object") {
      if (typeof item.field_name === "string") {
        name = item.field_name;
        location = item.field_name;
        message = typeof item.error === "string" ? item.error : typeof item.message === "string" ? item.message : undefined;
      } else if (Array.isArray(item.loc)) {
        const last = item.loc[item.loc.length - 1];
        if (typeof last === "string") name = last;
        location = item.loc.filter((part: unknown) => part !== "body").join(".");
        message = typeof item.msg === "string" ? item.msg : undefined;
      }
    }

    const text = message || "Invalid value";
    if (name && known.has(name)) {
      if (!fieldErrors[name]) fieldErrors[name] = text;
    } else {
      otherMessages.push(location ? `${location}: ${text}` : text);
    }
  }

  return { fieldErrors, otherMessages };
}

