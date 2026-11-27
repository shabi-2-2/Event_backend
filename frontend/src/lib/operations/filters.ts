/** Converts an HTML `datetime-local` value into a timezone-aware UTC string. */
export function datetimeLocalToUtc(value: string): string | undefined {
  const input = value.trim();
  if (!input) {
    return undefined;
  }

  const date = new Date(input);
  return Number.isNaN(date.getTime()) ? undefined : date.toISOString();
}

/** Mirrors the backend's `0–20` attempt filter bounds. */
export function parseAttemptFilter(value: string): number | undefined {
  const input = value.trim();
  if (!input) {
    return undefined;
  }

  const parsed = Number(input);
  if (!Number.isInteger(parsed) || parsed < 0 || parsed > 20) {
    return undefined;
  }

  return parsed;
}

export function isUuid(value: string): boolean {
  return /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i.test(
    value.trim(),
  );
}
