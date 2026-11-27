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
