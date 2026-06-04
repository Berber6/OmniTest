/** Format an ISO datetime string to local time (24-hour, Beijing time).
 *
 * Backend stores UTC timestamps via datetime.utcnow(), which produce
 * ISO strings without timezone markers (e.g. "2026-06-01T08:21:25").
 * This function adds "Z" to indicate UTC, then formats to local time
 * with 24-hour format.
 */
export function formatDateTime(isoString: string): string {
  let normalized = isoString;
  if (!normalized.endsWith("Z") && !normalized.includes("+") && !normalized.includes("+00:00")) {
    normalized = normalized + "Z";
  }
  const date = new Date(normalized);
  return date.toLocaleString("zh-CN", {
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
    hour12: false,
  });
}