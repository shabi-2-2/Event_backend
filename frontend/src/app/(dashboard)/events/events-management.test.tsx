import { fireEvent, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { renderManagement } from "@/test/management-test-utils";
import { ApiError } from "@/lib/api/errors";
import type { EventRecord } from "@/lib/api/contracts";

const navigation = vi.hoisted(() => ({
  push: vi.fn(),
  replace: vi.fn(),
}));

const api = vi.hoisted(() => ({
  events: {
    list: vi.fn(),
    get: vi.fn(),
    create: vi.fn(),
    update: vi.fn(),
    publish: vi.fn(),
    archive: vi.fn(),
  },
}));

const selection = vi.hoisted(() => ({
  selectedEventSlug: null as string | null,
  selectEvent: vi.fn(),
}));

vi.mock("next/navigation", () => ({
  useRouter: () => navigation,
  useParams: () => ({ eventSlug: "summit-2026" }),
  usePathname: () => "/events",
  useSearchParams: () => new URLSearchParams(),
}));

vi.mock("@/components/providers/api-client-provider", () => ({
  useApiClient: () => api,
}));

vi.mock("@/components/layout/event-selection-context", () => ({
  useEventSelection: () => selection,
}));

vi.mock("sonner", () => ({ toast: { success: vi.fn(), error: vi.fn() } }));

import EventsPage from "@/app/(dashboard)/events/page";
import NewEventPage from "@/app/(dashboard)/events/new/page";
import EventDetailPage from "@/app/(dashboard)/events/[eventSlug]/page";
import EditEventPage from "@/app/(dashboard)/events/[eventSlug]/edit/page";

const draftEvent: EventRecord = {
  slug: "summit-2026",
  name: "Summit 2026",
  description: null,
  starts_at: "2026-09-20T09:00:00.000Z",
  ends_at: "2026-09-20T17:00:00.000Z",
  timezone: "UTC",
  venue: "Main Hall",
  capacity: 200,
  registration_opens_at: null,
  registration_closes_at: null,
  status: "draft",
  created_at: "2026-05-01T00:00:00.000Z",
  updated_at: "2026-05-01T00:00:00.000Z",
};

function renderWithProvider(ui: React.ReactNode) {
  return renderManagement(<>{ui}</>);
}

describe("event management pages", () => {
  beforeEach(() => {
    navigation.push.mockReset();
    navigation.replace.mockReset();
    selection.selectEvent.mockReset();
    selection.selectedEventSlug = null;

    for (const fn of Object.values(api.events)) {
      fn.mockReset();
    }

    api.events.list.mockResolvedValue({
      items: [draftEvent],
      page: 1,
      page_size: 12,
      total: 1,
    });
    api.events.get.mockResolvedValue(draftEvent);
    api.events.create.mockResolvedValue(draftEvent);
    api.events.update.mockResolvedValue(draftEvent);
    api.events.publish.mockResolvedValue({ ...draftEvent, status: "published" });
    api.events.archive.mockResolvedValue({ ...draftEvent, status: "archived" });
  });

  it("lists events with pagination and status filter", async () => {
    const { container } = renderWithProvider(<EventsPage />);

    expect(await screen.findByText("Summit 2026")).toBeInTheDocument();
    expect(api.events.list).toHaveBeenCalledWith(
      expect.objectContaining({ page: 1, page_size: 12, status: undefined }),
      expect.any(AbortSignal),
    );
    expect(container.querySelector('[aria-label="Events"]')).toBeTruthy();

    fireEvent.change(screen.getByLabelText("Filter events by status"), {
      target: { value: "published" },
    });

    await waitFor(() => {
      expect(api.events.list).toHaveBeenLastCalledWith(
        expect.objectContaining({ status: "published" }),
        expect.any(AbortSignal),
      );
    });
  });

  it("shows an empty state and an error state on the event list", async () => {
    api.events.list.mockResolvedValueOnce({
      items: [],
      page: 1,
      page_size: 12,
      total: 0,
    });
    const view = renderWithProvider(<EventsPage />);
    expect(await screen.findByText("No events found")).toBeInTheDocument();
    view.unmount();

    api.events.list.mockRejectedValueOnce(new ApiError(403, "FORBIDDEN", "Denied."));
    renderWithProvider(<EventsPage />);
    expect(await screen.findByText("Access restricted")).toBeInTheDocument();
  });

  it("creates an event and navigates to its detail page", async () => {
    renderWithProvider(<NewEventPage />);

    fireEvent.change(screen.getByLabelText("Slug"), {
      target: { value: "summit-2026" },
    });
    fireEvent.change(screen.getByLabelText("Name"), { target: { value: "Summit 2026" } });
    fireEvent.change(screen.getByLabelText("Starts at (UTC)"), {
      target: { value: "2026-09-20T09:00" },
    });
    fireEvent.change(screen.getByLabelText("Ends at (UTC)"), {
      target: { value: "2026-09-20T17:00" },
    });

    fireEvent.click(screen.getByRole("button", { name: "Create event" }));

    await waitFor(() => {
      expect(api.events.create).toHaveBeenCalledWith(
        expect.objectContaining({
          slug: "summit-2026",
          name: "Summit 2026",
          starts_at: "2026-09-20T09:00:00Z",
          ends_at: "2026-09-20T17:00:00Z",
        }),
      );
    });
    await waitFor(() => {
      expect(navigation.push).toHaveBeenCalledWith("/events/summit-2026");
    });
  });

  it("shows backend validation errors on the event form", async () => {
    api.events.create.mockRejectedValueOnce(
      new ApiError(422, "VALIDATION_ERROR", "Invalid request", [
        { loc: ["body", "name"], msg: "Name is too long." },
      ]),
    );
    renderWithProvider(<NewEventPage />);

    fireEvent.change(screen.getByLabelText("Slug"), {
      target: { value: "summit-2026" },
    });
    fireEvent.change(screen.getByLabelText("Name"), { target: { value: "Summit 2026" } });
    fireEvent.change(screen.getByLabelText("Starts at (UTC)"), {
      target: { value: "2026-09-20T09:00" },
    });
    fireEvent.change(screen.getByLabelText("Ends at (UTC)"), {
      target: { value: "2026-09-20T17:00" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Create event" }));

    expect(await screen.findByText("Name is too long.")).toBeInTheDocument();
    expect((await screen.findAllByText("Invalid request")).length).toBeGreaterThan(0);
  });

  it("publishes and archives only supported lifecycle transitions", async () => {
    const view = renderWithProvider(<EventDetailPage />);
    expect((await screen.findAllByText("Summit 2026")).length).toBeGreaterThan(0);

    fireEvent.click(screen.getByRole("button", { name: "Publish" }));
    const confirmPublish = await screen.findByRole("button", {
      name: "Publish event",
    });
    fireEvent.click(confirmPublish);

    await waitFor(() => {
      expect(api.events.publish).toHaveBeenCalledWith("summit-2026");
    });

    api.events.get.mockResolvedValue({ ...draftEvent, status: "published" });
    view.unmount();
    const publishedView = renderWithProvider(<EventDetailPage />);
    expect((await publishedView.findAllByText("Summit 2026")).length).toBeGreaterThan(0);

    fireEvent.click(screen.getByRole("button", { name: "Archive" }));
    fireEvent.click(
      await screen.findByRole("button", { name: "Archive event" }),
    );

    await waitFor(() => {
      expect(api.events.archive).toHaveBeenCalledWith("summit-2026");
    });
  });

  it("does not offer lifecycle actions for cancelled events", async () => {
    api.events.get.mockResolvedValue({ ...draftEvent, status: "cancelled" });
    renderWithProvider(<EventDetailPage />);
    expect((await screen.findAllByText("Summit 2026")).length).toBeGreaterThan(0);
    expect(screen.queryByRole("button", { name: "Publish" })).toBeNull();
    expect(screen.queryByRole("button", { name: "Archive" })).toBeNull();
  });

  it("edits an event without sending slug or status", async () => {
    renderWithProvider(<EditEventPage />);
    expect(await screen.findByDisplayValue("Summit 2026")).toBeInTheDocument();

    fireEvent.change(screen.getByLabelText("Name"), {
      target: { value: "Summit 2026 Updated" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Save changes" }));

    await waitFor(() => {
      expect(api.events.update).toHaveBeenCalledWith(
        "summit-2026",
        expect.not.objectContaining({ slug: expect.anything(), status: expect.anything() }),
      );
    });
    expect(api.events.update.mock.calls[0][1].name).toBe("Summit 2026 Updated");
  });
});
