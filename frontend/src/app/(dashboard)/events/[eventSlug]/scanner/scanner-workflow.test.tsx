import { QueryClientProvider } from "@tanstack/react-query";
import { act, fireEvent, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { renderManagement } from "@/test/management-test-utils";
import type {
  CheckinResponse,
  CheckinOutcome,
  ScannerTicketInfo,
} from "@/lib/api/contracts";
import { ApiError } from "@/lib/api/errors";
import { dashboardKeys, managementKeys } from "@/lib/api/query-keys";
import ScannerPage from "@/app/(dashboard)/events/[eventSlug]/scanner/page";

const TOKEN = "raw-ticket-token-1234567890";
const SECOND_TOKEN = "second-raw-token-123456789";

type CameraCallbacks = {
  onReady: () => void;
  onDenied: (error: { title: string; description: string; retryable: boolean }) => void;
  onUnavailable: (error: { title: string; description: string; retryable: boolean }) => void;
  onDetected: (token: string) => void;
};

const params = vi.hoisted(() => ({ eventSlug: "summit-2026" }));

const api = vi.hoisted(() => ({
  checkins: {
    verify: vi.fn(),
    confirm: vi.fn(),
  },
}));

const camera = vi.hoisted(() => ({
  videoRef: { current: null as HTMLVideoElement | null },
  start: vi.fn(),
  stop: vi.fn(),
  callbacks: null as unknown,
}));

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: vi.fn(), replace: vi.fn() }),
  useParams: () => params,
  usePathname: () => `/events/${params.eventSlug}/scanner`,
  useSearchParams: () => new URLSearchParams(),
}));

vi.mock("@/components/providers/api-client-provider", () => ({
  useApiClient: () => api,
}));

vi.mock("@/lib/scanner/use-qr-camera", () => ({
  useQrCamera: (callbacks: CameraCallbacks) => {
    camera.callbacks = callbacks;

    return {
      videoRef: camera.videoRef,
      start: camera.start,
      stop: camera.stop,
    };
  },
}));

const ticket: ScannerTicketInfo = {
  attendee_name: "Ada Lovelace",
  urn: "student-1",
  ticket_status: "active",
  registration_status: "registered",
  check_in_status: "pending",
};

function scannerResponse(
  outcome: CheckinOutcome,
  ticketInfo: ScannerTicketInfo | null = ticket,
): CheckinResponse {
  return {
    success: outcome === "valid_ticket" || outcome === "checked_in",
    outcome,
    message: `Backend result: ${outcome}`,
    ticket: ticketInfo,
  };
}

function deferred<T>() {
  let resolve!: (value: T) => void;
  let reject!: (error: unknown) => void;
  const promise = new Promise<T>((res, rej) => {
    resolve = res;
    reject = rej;
  });

  return { promise, resolve, reject };
}

function callbacks(): CameraCallbacks {
  return {
    onReady: vi.fn(),
    onDenied: vi.fn(),
    onUnavailable: vi.fn(),
    onDetected: vi.fn(),
  };
}

function submitManualToken(value = TOKEN) {
  fireEvent.change(screen.getByLabelText("Raw ticket token"), {
    target: { value },
  });
  fireEvent.click(screen.getByRole("button", { name: "Verify token" }));
}

describe("QR scanner workflow", () => {
  beforeEach(() => {
    params.eventSlug = "summit-2026";
    api.checkins.verify.mockReset();
    api.checkins.confirm.mockReset();
    camera.start.mockReset().mockResolvedValue(undefined);
    camera.stop.mockReset();
    camera.callbacks = callbacks();
    api.checkins.verify.mockResolvedValue(scannerResponse("valid_ticket"));
    api.checkins.confirm.mockResolvedValue(scannerResponse("checked_in"));
  });

  it("exposes accessible, responsive controls and only starts on explicit action", async () => {
    renderManagement(<ScannerPage />);
    camera.stop.mockClear();

    const status = screen.getByRole("status");
    expect(status).toHaveAttribute("aria-live", "polite");
    expect(status).toHaveTextContent("Scanner ready");

    const startButton = screen.getByRole("button", { name: "Start camera" });
    expect(startButton.className).toContain("sm:w-auto");
    fireEvent.click(startButton);
    expect(camera.start).toHaveBeenCalledTimes(1);

    act(() => {
      (camera.callbacks as CameraCallbacks).onReady();
    });

    expect(screen.getByLabelText("Ticket QR scanner camera preview")).toBeVisible();
    fireEvent.click(screen.getByRole("button", { name: "Stop camera" }));
    expect(camera.stop).toHaveBeenCalledTimes(1);
    await waitFor(() => {
      expect(screen.getByRole("status")).toHaveTextContent("Scanner ready");
    });
  });

  it("verifies a manual raw token, then requires explicit confirmation", async () => {
    renderManagement(<ScannerPage />);
    submitManualToken();

    expect(
      await screen.findByRole("button", { name: "Confirm check-in" }),
    ).toBeInTheDocument();
    expect(api.checkins.verify).toHaveBeenCalledWith(
      "summit-2026",
      { ticket_token: TOKEN },
      expect.any(AbortSignal),
    );
    expect(api.checkins.confirm).not.toHaveBeenCalled();
    expect(screen.getByText("Ada Lovelace")).toBeInTheDocument();
    expect(screen.getByText("student-1")).toBeInTheDocument();
    expect(screen.queryByText(TOKEN)).toBeNull();

    fireEvent.click(screen.getByRole("button", { name: "Cancel" }));

    await waitFor(() => {
      expect(screen.queryByText("Ada Lovelace")).toBeNull();
    });
    expect(api.checkins.confirm).not.toHaveBeenCalled();
  });

  it("confirms only after explicit action and invalidates event data", async () => {
    const view = renderManagement(<ScannerPage />);
    const invalidate = vi.spyOn(view.queryClient, "invalidateQueries");

    submitManualToken();
    await screen.findByRole("button", { name: "Confirm check-in" });

    fireEvent.change(screen.getByLabelText("Station (optional)"), {
      target: { value: "Door 1" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Confirm check-in" }));

    expect(
      await screen.findByText("Backend result: checked_in"),
    ).toBeInTheDocument();
    expect(api.checkins.confirm).toHaveBeenCalledWith(
      "summit-2026",
      { ticket_token: TOKEN, station: "Door 1" },
      expect.any(AbortSignal),
    );
    expect(invalidate).toHaveBeenCalledWith({
      queryKey: managementKeys.attendeesAll("summit-2026"),
    });
    expect(invalidate).toHaveBeenCalledWith({
      queryKey: managementKeys.registrationsAll("summit-2026"),
    });
    expect(invalidate).toHaveBeenCalledWith({
      queryKey: managementKeys.ticketsAll("summit-2026"),
    });
    expect(invalidate).toHaveBeenCalledWith({
      queryKey: dashboardKeys.forEvent("summit-2026"),
    });
  });

  it("prevents a second confirmation while one is in flight", async () => {
    const pending = deferred<CheckinResponse>();
    api.checkins.confirm.mockReturnValue(pending.promise);
    renderManagement(<ScannerPage />);

    submitManualToken();
    await screen.findByRole("button", { name: "Confirm check-in" });

    fireEvent.click(screen.getByRole("button", { name: "Confirm check-in" }));
    fireEvent.click(screen.getByRole("button", { name: "Confirming…" }));

    expect(api.checkins.confirm).toHaveBeenCalledTimes(1);

    await act(async () => {
      pending.resolve(scannerResponse("checked_in"));
      await pending.promise;
    });

    expect(await screen.findByText("Check-in confirmed")).toBeInTheDocument();
  });

  it("validates station input without sending a confirmation request", async () => {
    renderManagement(<ScannerPage />);
    submitManualToken();
    await screen.findByRole("button", { name: "Confirm check-in" });

    fireEvent.change(screen.getByLabelText("Station (optional)"), {
      target: { value: "Door/1" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Confirm check-in" }));

    expect(screen.getByText(/up to 100 letters/i)).toBeInTheDocument();
    expect(api.checkins.confirm).not.toHaveBeenCalled();
  });

  it.each<[CheckinOutcome, string]>([
    ["invalid_ticket", "Invalid ticket"],
    ["revoked_ticket", "Revoked ticket"],
    ["expired_ticket", "Expired ticket"],
    ["registration_cancelled", "Registration cancelled"],
    ["invalid_registration_state", "Registration not eligible"],
    ["already_checked_in", "Already checked in"],
  ])("shows the authoritative %s result without confirming", async (outcome, title) => {
    api.checkins.verify.mockResolvedValue(
      scannerResponse(outcome, outcome === "invalid_ticket" ? null : ticket),
    );
    renderManagement(<ScannerPage />);
    submitManualToken();

    expect(await screen.findByText(title)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Confirm check-in" })).toBeNull();
    expect(api.checkins.confirm).not.toHaveBeenCalled();
  });

  it.each<[number, string]>([
    [401, "Authentication required"],
    [403, "Scanner access denied"],
    [404, "Event unavailable"],
    [409, "Check-in conflict"],
    [422, "Token not accepted"],
    [429, "Too many requests"],
    [500, "Scanner service error"],
  ])("maps HTTP %i into a scanner error state", async (status, title) => {
    api.checkins.verify.mockRejectedValue(new ApiError(status, "ERROR", "server detail"));
    renderManagement(<ScannerPage />);
    submitManualToken();

    await waitFor(() => {
      expect(screen.getByRole("alert")).toHaveTextContent(title);
    });
    expect(api.checkins.confirm).not.toHaveBeenCalled();
  });

  it("maps network failures and unexpected response shapes", async () => {
    api.checkins.verify.mockRejectedValueOnce(new Error("offline"));
    const network = renderManagement(<ScannerPage />);
    submitManualToken();
    await waitFor(() => {
      expect(screen.getByRole("alert")).toHaveTextContent("Network error");
    });

    network.unmount();
    api.checkins.verify.mockResolvedValueOnce({ success: true, outcome: "mystery" });
    renderManagement(<ScannerPage />);
    submitManualToken();
    await waitFor(() => {
      expect(screen.getByRole("alert")).toHaveTextContent("Unexpected scanner response");
    });
  });

  it("deduplicates repeated QR detections before verification", async () => {
    renderManagement(<ScannerPage />);

    act(() => {
      const handlers = camera.callbacks as CameraCallbacks;
      handlers.onReady();
      handlers.onDetected(TOKEN);
      handlers.onDetected(TOKEN);
      handlers.onDetected(SECOND_TOKEN);
    });

    await screen.findByRole("button", { name: "Confirm check-in" });
    expect(api.checkins.verify).toHaveBeenCalledTimes(1);
    expect(api.checkins.verify).toHaveBeenCalledWith(
      "summit-2026",
      { ticket_token: TOKEN },
      expect.any(AbortSignal),
    );
  });

  it("surfaces camera denial and unavailability while keeping manual entry available", async () => {
    renderManagement(<ScannerPage />);
    fireEvent.click(screen.getByRole("button", { name: "Start camera" }));

    act(() => {
      (camera.callbacks as CameraCallbacks).onDenied({
        title: "Camera permission denied",
        description: "Allow camera access.",
        retryable: false,
      });
    });

    await waitFor(() => {
      expect(screen.getByRole("alert")).toHaveTextContent("Camera permission denied");
    });
    expect(screen.getByLabelText("Raw ticket token")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Try camera again" }));
    act(() => {
      (camera.callbacks as CameraCallbacks).onUnavailable({
        title: "Camera unavailable",
        description: "No camera found.",
        retryable: true,
      });
    });

    await waitFor(() => {
      expect(screen.getByRole("alert")).toHaveTextContent("Camera unavailable");
    });
  });

  it("discards an old event's in-flight verification after event switching", async () => {
    const pending = deferred<CheckinResponse>();
    api.checkins.verify.mockReturnValueOnce(pending.promise);
    const view = renderManagement(<ScannerPage />);

    submitManualToken();
    await waitFor(() => {
      expect(api.checkins.verify).toHaveBeenCalledWith(
        "summit-2026",
        { ticket_token: TOKEN },
        expect.any(AbortSignal),
      );
    });

    params.eventSlug = "summit-2027";
    view.rerender(
      <QueryClientProvider client={view.queryClient}>
        <ScannerPage />
      </QueryClientProvider>,
    );
    await waitFor(() => {
      expect(screen.getByRole("button", { name: "Start camera" })).toBeInTheDocument();
    });

    await act(async () => {
      pending.resolve(scannerResponse("valid_ticket"));
      await pending.promise;
    });

    expect(screen.queryByText("Ada Lovelace")).toBeNull();
    expect(screen.queryByRole("button", { name: "Confirm check-in" })).toBeNull();

    const otherTicket = { ...ticket, attendee_name: "Grace Hopper" };
    api.checkins.verify.mockResolvedValueOnce(scannerResponse("valid_ticket", otherTicket));
    submitManualToken(SECOND_TOKEN);

    expect(
      await screen.findByRole("button", { name: "Confirm check-in" }),
    ).toBeInTheDocument();
    expect(api.checkins.verify).toHaveBeenLastCalledWith(
      "summit-2027",
      { ticket_token: SECOND_TOKEN },
      expect.any(AbortSignal),
    );
    expect(screen.getByText("Grace Hopper")).toBeInTheDocument();
  });
});
