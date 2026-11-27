import { z } from "zod";
import type {
  EventCreateRequest,
  EventRecord,
  EventUpdateRequest,
} from "@/lib/api/contracts";

const SLUG_PATTERN = /^[a-z0-9]+(?:-[a-z0-9]+)*$/;
const DATE_TIME_LOCAL_PATTERN = /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}(?::\d{2})?$/;

export const eventFormSchema = z
  .object({
    slug: z
      .string()
      .trim()
      .min(3, "Slug must be at least 3 characters.")
      .max(100, "Slug must be at most 100 characters.")
      .regex(SLUG_PATTERN, "Use lowercase letters, numbers, and single hyphens."),
    name: z.string().trim().min(1, "Name is required.").max(200, "Name must be at most 200 characters."),
    description: z.string().max(5000, "Description must be at most 5000 characters."),
    starts_at: z
      .string()
      .regex(DATE_TIME_LOCAL_PATTERN, "Enter a valid start date and time."),
    ends_at: z
      .string()
      .regex(DATE_TIME_LOCAL_PATTERN, "Enter a valid end date and time."),
    timezone: z.string().trim().min(1, "Time zone is required.").max(64, "Time zone must be at most 64 characters."),
    venue: z.string().trim().max(200, "Venue must be at most 200 characters."),
    capacity: z
      .string()
      .refine((value) => {
        const trimmed = value.trim();
        if (!trimmed) return true;
        const number = Number(trimmed);
        return /^\d+$/.test(trimmed) && number >= 1 && number <= 1_000_000;
      }, "Capacity must be between 1 and 1,000,000."),
    registration_opens_at: z.union([z.literal(""), z.string().regex(DATE_TIME_LOCAL_PATTERN, "Enter a valid registration open time.")]),
    registration_closes_at: z.union([z.literal(""), z.string().regex(DATE_TIME_LOCAL_PATTERN, "Enter a valid registration close time.")]),
  })
  .superRefine((values, context) => {
    const starts = toIsoFromInput(values.starts_at);
    const ends = toIsoFromInput(values.ends_at);
    const opens = toIsoFromInput(values.registration_opens_at);
    const closes = toIsoFromInput(values.registration_closes_at);

    if (!starts || !ends) {
      context.addIssue({
        code: z.ZodIssueCode.custom,
        path: [!starts ? "starts_at" : "ends_at"],
        message: "Enter a valid calendar date and time.",
      });
      return;
    }

    const startsMs = Date.parse(starts);
    const endsMs = Date.parse(ends);
    if (Number.isNaN(startsMs) || Number.isNaN(endsMs)) {
      context.addIssue({
        code: z.ZodIssueCode.custom,
        path: ["starts_at"],
        message: "Enter a valid calendar date and time.",
      });
      return;
    }

    if (endsMs <= startsMs) {
      context.addIssue({
        code: z.ZodIssueCode.custom,
        path: ["ends_at"],
        message: "End time must be after the start time.",
      });
    }

    if (opens) {
      const opensMs = Date.parse(opens);
      if (Number.isNaN(opensMs) || opensMs >= startsMs) {
        context.addIssue({
          code: z.ZodIssueCode.custom,
          path: ["registration_opens_at"],
          message: "Registration must open before the event starts.",
        });
      }
    }

    if (closes) {
      const closesMs = Date.parse(closes);
      if (Number.isNaN(closesMs) || closesMs > startsMs) {
        context.addIssue({
          code: z.ZodIssueCode.custom,
          path: ["registration_closes_at"],
          message: "Registration must close by the event start time.",
        });
      }
    }

    if (opens && closes && Date.parse(closes) <= Date.parse(opens)) {
      context.addIssue({
        code: z.ZodIssueCode.custom,
        path: ["registration_closes_at"],
        message: "Registration close time must be after the open time.",
      });
    }

    try {
      new Intl.DateTimeFormat("en-US", { timeZone: values.timezone });
    } catch {
      context.addIssue({
        code: z.ZodIssueCode.custom,
        path: ["timezone"],
        message: "Enter a valid IANA time zone, such as UTC or America/New_York.",
      });
    }
  });

export type EventFormValues = z.infer<typeof eventFormSchema>;

export function toIsoFromInput(value: string): string | null {
  if (!value) return null;

  const normalized = value.length === 16 ? `${value}:00Z` : `${value}Z`;
  return Number.isNaN(Date.parse(normalized)) ? null : normalized;
}

function toInputFromIso(value: string | null | undefined): string {
  if (!value) return "";
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? "" : date.toISOString().slice(0, 16);
}

export function eventToFormValues(event: EventRecord): EventFormValues {
  return {
    slug: event.slug,
    name: event.name,
    description: event.description ?? "",
    starts_at: toInputFromIso(event.starts_at),
    ends_at: toInputFromIso(event.ends_at),
    timezone: event.timezone,
    venue: event.venue ?? "",
    capacity: event.capacity ? String(event.capacity) : "",
    registration_opens_at: toInputFromIso(event.registration_opens_at),
    registration_closes_at: toInputFromIso(event.registration_closes_at),
  };
}

export function valuesToEventCreate(values: EventFormValues): EventCreateRequest {
  return {
    slug: values.slug.trim().toLowerCase(),
    name: values.name.trim(),
    description: values.description.trim() || null,
    starts_at: toIsoFromInput(values.starts_at)!,
    ends_at: toIsoFromInput(values.ends_at)!,
    timezone: values.timezone.trim(),
    venue: values.venue.trim() || null,
    capacity: values.capacity.trim() ? Number(values.capacity) : null,
    registration_opens_at: toIsoFromInput(values.registration_opens_at),
    registration_closes_at: toIsoFromInput(values.registration_closes_at),
  };
}

export function valuesToEventUpdate(values: EventFormValues): EventUpdateRequest {
  return {
    name: values.name.trim(),
    description: values.description.trim() || null,
    starts_at: toIsoFromInput(values.starts_at)!,
    ends_at: toIsoFromInput(values.ends_at)!,
    timezone: values.timezone.trim(),
    venue: values.venue.trim() || null,
    capacity: values.capacity.trim() ? Number(values.capacity) : null,
    registration_opens_at: toIsoFromInput(values.registration_opens_at),
    registration_closes_at: toIsoFromInput(values.registration_closes_at),
  };
}
