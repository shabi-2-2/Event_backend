import { describe, expect, it } from "vitest";
import type { EventRecord } from "@/lib/api/contracts";
import {
  eventFormSchema,
  eventToFormValues,
  toIsoFromInput,
  valuesToEventCreate,
  valuesToEventUpdate,
  type EventFormValues,
} from "@/lib/management/event-form";

function validValues(overrides: Partial<EventFormValues> = {}): EventFormValues {
  return {
    slug: "test-event",
    name: "Test Event",
    description: "",
    starts_at: "2026-06-20T09:00",
    ends_at: "2026-06-20T17:00",
    timezone: "UTC",
    venue: "",
    capacity: "",
    registration_opens_at: "",
    registration_closes_at: "",
    ...overrides,
  };
}

describe("eventFormSchema", () => {
  it("accepts valid values", () => {
    expect(eventFormSchema.safeParse(validValues()).success).toBe(true);
  });

  it("rejects invalid slugs", () => {
    for (const slug of ["ab", "UPPER", "has spaces", "two--hyphens", "-leading"]) {
      expect(eventFormSchema.safeParse(validValues({ slug })).success).toBe(false);
    }
  });

  it("rejects empty names and overlong descriptions", () => {
    expect(eventFormSchema.safeParse(validValues({ name: "" })).success).toBe(false);
    expect(
      eventFormSchema.safeParse(validValues({ description: "x".repeat(5001) })).success,
    ).toBe(false);
  });

  it("requires end time after start time", () => {
    const result = eventFormSchema.safeParse(
      validValues({ ends_at: "2026-06-20T08:00" }),
    );
    expect(result.success).toBe(false);
    if (!result.success) {
      expect(result.error.issues.some((issue) => issue.path[0] === "ends_at")).toBe(true);
    }
  });

  it("enforces registration window rules", () => {
    expect(
      eventFormSchema.safeParse(
        validValues({ registration_opens_at: "2026-06-20T10:00" }),
      ).success,
    ).toBe(false);

    expect(
      eventFormSchema.safeParse(
        validValues({ registration_closes_at: "2026-06-20T18:00" }),
      ).success,
    ).toBe(false);

    expect(
      eventFormSchema.safeParse(
        validValues({
          registration_opens_at: "2026-06-20T09:00",
          registration_closes_at: "2026-06-20T08:00",
        }),
      ).success,
    ).toBe(false);

    expect(
      eventFormSchema.safeParse(
        validValues({
          registration_opens_at: "2026-01-01T00:00",
          registration_closes_at: "2026-06-19T23:00",
        }),
      ).success,
    ).toBe(true);
  });

  it("rejects invalid capacity and timezone", () => {
    expect(eventFormSchema.safeParse(validValues({ capacity: "0" })).success).toBe(false);
    expect(
      eventFormSchema.safeParse(validValues({ capacity: "1000001" })).success,
    ).toBe(false);
    expect(eventFormSchema.safeParse(validValues({ capacity: "100" })).success).toBe(true);
    expect(
      eventFormSchema.safeParse(validValues({ timezone: "Not/AZone" })).success,
    ).toBe(false);
  });
});

describe("event form transforms", () => {
  it("converts local inputs to timezone-aware UTC ISO strings", () => {
    expect(toIsoFromInput("2026-06-20T09:00")).toBe("2026-06-20T09:00:00Z");
    expect(toIsoFromInput("2026-06-20T09:30:15")).toBe("2026-06-20T09:30:15Z");
    expect(toIsoFromInput("")).toBeNull();
  });

  it("builds a create request with nullable optional fields", () => {
    const request = valuesToEventCreate(validValues());
    expect(request).toEqual({
      slug: "test-event",
      name: "Test Event",
      description: null,
      starts_at: "2026-06-20T09:00:00Z",
      ends_at: "2026-06-20T17:00:00Z",
      timezone: "UTC",
      venue: null,
      capacity: null,
      registration_opens_at: null,
      registration_closes_at: null,
    });
  });

  it("builds an update request without slug or status", () => {
    const request = valuesToEventUpdate(
      validValues({ capacity: "250", venue: "Main Hall" }),
    );
    expect(request).not.toHaveProperty("slug");
    expect(request).not.toHaveProperty("status");
    expect(request.capacity).toBe(250);
    expect(request.venue).toBe("Main Hall");
    expect(request.starts_at).toBe("2026-06-20T09:00:00Z");
  });

  it("hydrates form values from an event record", () => {
    const event: EventRecord = {
      slug: "test-event",
      name: "Test Event",
      description: "A description",
      starts_at: "2026-06-20T09:00:00.000Z",
      ends_at: "2026-06-20T17:00:00.000Z",
      timezone: "UTC",
      venue: "Main Hall",
      capacity: 250,
      registration_opens_at: "2026-01-01T00:00:00.000Z",
      registration_closes_at: null,
      status: "published",
      created_at: "2026-05-01T00:00:00.000Z",
      updated_at: "2026-05-01T00:00:00.000Z",
    };

    expect(eventToFormValues(event)).toEqual({
      slug: "test-event",
      name: "Test Event",
      description: "A description",
      starts_at: "2026-06-20T09:00",
      ends_at: "2026-06-20T17:00",
      timezone: "UTC",
      venue: "Main Hall",
      capacity: "250",
      registration_opens_at: "2026-01-01T00:00",
      registration_closes_at: "",
    });
  });
});
