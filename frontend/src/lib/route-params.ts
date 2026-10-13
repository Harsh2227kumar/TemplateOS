/** Positive integer id from a route param such as "/templates/:id"; null when it is not one. */
export function parseRouteId(param: string | undefined): number | null {
  if (!param || !/^\d+$/.test(param)) return null;
  const id = Number(param);
  return id > 0 && Number.isSafeInteger(id) ? id : null;
}
