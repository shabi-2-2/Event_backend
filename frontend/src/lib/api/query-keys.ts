function paramsKey(params: Record<string, unknown> = {}): string {
  return JSON.stringify(params);
}

export const dashboardKeys = {
  all: ["dashboard"] as const,
  forEvent: (slug: string) => [...dashboardKeys.all, slug] as const,
  events: () => [...dashboardKeys.all, "accessible-events"] as const,
  event: (slug: string) => [...dashboardKeys.forEvent(slug), "event"] as const,
  overview: (slug: string) => [...dashboardKeys.forEvent(slug), "overview"] as const,
  registrations: (slug: string, rangeKey: string) =>
    [...dashboardKeys.forEvent(slug), "registrations", rangeKey] as const,
  attendance: (slug: string, rangeKey: string) =>
    [...dashboardKeys.forEvent(slug), "attendance", rangeKey] as const,
  emailDeliveries: (slug: string) =>
    [...dashboardKeys.forEvent(slug), "email-deliveries"] as const,
};

export const managementKeys = {
  all: ["management"] as const,
  eventsAll: () => [...managementKeys.all, "events"] as const,
  events: (params: Record<string, unknown> = {}) =>
    [...managementKeys.eventsAll(), paramsKey(params)] as const,
  forEvent: (slug: string) => [...managementKeys.all, slug] as const,
  event: (slug: string) => [...managementKeys.forEvent(slug), "event"] as const,
  attendeesAll: (slug: string) =>
    [...managementKeys.forEvent(slug), "attendees"] as const,
  attendees: (slug: string, params: Record<string, unknown> = {}) =>
    [...managementKeys.attendeesAll(slug), paramsKey(params)] as const,
  attendee: (slug: string, reference: string) =>
    [...managementKeys.forEvent(slug), "attendee", reference] as const,
  registrationsAll: (slug: string) =>
    [...managementKeys.forEvent(slug), "registrations"] as const,
  registrations: (slug: string, params: Record<string, unknown> = {}) =>
    [...managementKeys.registrationsAll(slug), paramsKey(params)] as const,
  registration: (slug: string, reference: string) =>
    [...managementKeys.forEvent(slug), "registration", reference] as const,
  ticketsAll: (slug: string) => [...managementKeys.forEvent(slug), "tickets"] as const,
  tickets: (slug: string, params: Record<string, unknown> = {}) =>
    [...managementKeys.ticketsAll(slug), paramsKey(params)] as const,
  staffAll: (slug: string) => [...managementKeys.forEvent(slug), "staff"] as const,
  staff: (slug: string, params: Record<string, unknown> = {}) =>
    [...managementKeys.staffAll(slug), paramsKey(params)] as const,
};
