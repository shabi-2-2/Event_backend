export function safeNextPath(value: string | string[] | null | undefined): string {
  const candidate = Array.isArray(value) ? value[0] : value;

  if (!candidate || !candidate.startsWith("/") || candidate.startsWith("//")) {
    return "/dashboard";
  }

  return candidate;
}

export function loginRedirectFor(next: string, reason?: "session_expired"): string {
  const params = new URLSearchParams({ next });

  if (reason) {
    params.set("reason", reason);
  }

  return `/login?${params.toString()}`;
}

export function requireAuthenticatedUser(
  user: { id: string } | null,
  next: string,
): string | null {
  return user ? null : loginRedirectFor(next);
}
