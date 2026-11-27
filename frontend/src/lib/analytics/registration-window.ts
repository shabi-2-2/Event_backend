import type { EventRecord } from "@/lib/api/contracts";
import { formatDateTime } from "@/lib/format";

export type RegistrationWindowStatus = {
  label: string;
  detail: string;
  tone: "neutral" | "success" | "warning";
};

/** Derives a display status from the event's backend timestamps; not a backend field. */
export function getRegistrationWindowStatus(
  event: EventRecord,
  now: Date = new Date(),
): RegistrationWindowStatus {
  if (!event.registration_opens_at && !event.registration_closes_at) {
    return { label: "Not configured", detail: "No registration window", tone: "neutral" };
  }

  const opensAt = event.registration_opens_at ? new Date(event.registration_opens_at) : null;
  const closesAt = event.registration_closes_at ? new Date(event.registration_closes_at) : null;
  const timestamp = now.getTime();

  if (opensAt && timestamp < opensAt.getTime()) {
    return {
      label: "Not open",
      detail: `Opens ${formatDateTime(event.registration_opens_at)}`,
      tone: "warning",
    };
  }

  if (closesAt && timestamp > closesAt.getTime()) {
    return {
      label: "Closed",
      detail: `Closed ${formatDateTime(event.registration_closes_at)}`,
      tone: "neutral",
    };
  }

  if (closesAt) {
    return {
      label: "Open",
      detail: `Until ${formatDateTime(event.registration_closes_at)}`,
      tone: "success",
    };
  }

  return {
    label: "Open",
    detail: `Since ${formatDateTime(event.registration_opens_at)}`,
    tone: "success",
  };
}
