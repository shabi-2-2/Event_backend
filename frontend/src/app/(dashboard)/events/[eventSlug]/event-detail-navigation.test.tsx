import { screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import type { EventRecord } from "@/lib/api/contracts";
import { renderManagement } from "@/test/management-test-utils";

const params = vi.hoisted(() => ({ eventSlug: "summit-2026" }));

const api = vi.hoisted(() => ({
  events: {
    get: vi.fn(),
    publish: vi.fn(),
    archive: vi.fn(),
  },
}));

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: vi.fn(), replace: vi.fn() }),
  useParams: () => params,
  usePathname: () => "/events/summit-2026",
  useSearchParams: () => new URLSearchParams(),
}));

vi.mock("@/components/providers/api-client-provider", () => ({
  useApiClient: () => api,
}));

vi.mock("sonner", () => ({ toast: { success: vi.fn(), error: vi.fn() } }));

import { EventSelectionProvider } from "@/components/layout/event-selection-context";
import EventDetailPage from "@/app/(dashboard)/events/[eventSlug]/page";

const event: EventRecord = {
  slug: "summit-2026",
  name: "Summit 2026",
  description: "Annual summit",
  starts_at: "2026-06-01T09:00:00Z",
  ends_at: "2026-06-02T17:00:00Z",
  timezone: "UTC",
  venue: "Online",
  capacity: 100,
  registration_opens_at: null,
  registration_closes_at: null,
  status: "published",
  created_at: "2026-05-01T00:00:00Z",
  updated_at: "2026-05-01T00:00:00Z",
};

describe("event detail operations navigation", () => {
  beforeEach(() => {
    params.eventSlug = "summit-2026";
    api.events.get.mockReset().mockResolvedValue(event);
  });

  it("links email operations, audit logs, and exports to the current event", async () => {
    renderManagement(
      <EventSelectionProvider>
        <EventDetailPage />
      </EventSelectionProvider>,
    );

    expect(
      await screen.findByRole("link", { name: "Open email operations" }),
    ).toHaveAttribute("href", "/events/summit-2026/email-deliveries");
    expect(screen.getByRole("link", { name: "Open audit logs" })).toHaveAttribute(
      "href",
      "/events/summit-2026/audit-logs",
    );
    expect(screen.getByRole("link", { name: "Open exports" })).toHaveAttribute(
      "href",
      "/events/summit-2026/exports",
    );
    expect(api.events.get).toHaveBeenCalledWith("summit-2026", expect.any(AbortSignal));
  });
});
