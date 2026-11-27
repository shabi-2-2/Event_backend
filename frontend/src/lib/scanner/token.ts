const TOKEN_MIN_LENGTH = 20;
const TOKEN_MAX_LENGTH = 256;
const STATION_PATTERN = /^[A-Za-z0-9][A-Za-z0-9 ._:-]{0,99}$/;

/** The QR payload is the raw token only; trim exactly as the backend does. */
export function normalizeTicketToken(value: string): string {
  return value.trim();
}

export function isTicketTokenValid(value: string): boolean {
  const token = normalizeTicketToken(value);
  return token.length >= TOKEN_MIN_LENGTH && token.length <= TOKEN_MAX_LENGTH;
}

/** Mirrors the backend station validator; the backend remains authoritative. */
export function normalizeStation(value: string): string | null {
  const station = value.trim();
  return station || null;
}

export function isStationValid(value: string): boolean {
  const station = normalizeStation(value);
  return station === null || STATION_PATTERN.test(station);
}
