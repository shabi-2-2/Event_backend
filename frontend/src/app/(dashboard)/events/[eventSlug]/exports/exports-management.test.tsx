import { fireEvent, screen, waitFor } from "@testing-library/react";
import { QueryClientProvider } from "@tanstack/react-query";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { DownloadedFile } from "@/lib/api/client";
import type { ExportDataset, ExportFormat } from "@/lib/api/contracts";
import { ApiError } from "@/lib/api/errors";
import {
  createNoRetryQueryClient,
  renderManagement,
} from "@/test/management-test-utils";

const params = vi.hoisted(() => ({ eventSlug: "summit-2026" }));

const api = vi.hoisted(() => ({
  exports: {
    download: vi.fn(),
  },
}));

const toast = vi.hoisted(() => ({ success: vi.fn(), error: vi.fn() }));

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: vi.fn(), replace: vi.fn() }),
  useParams: () => params,
  usePathname: () => "/events/summit-2026/exports",
  useSearchParams: () => new URLSearchParams(),
}));

vi.mock("@/components/providers/api-client-provider", () => ({
  useApiClient: () => api,
}));

vi.mock("sonner", () => ({ toast }));

import ExportsPage from "@/app/(dashboard)/events/[eventSlug]/exports/page";

function downloadedFile(dataset: ExportDataset, format: ExportFormat): DownloadedFile {
  if (format === "csv") {
    return {
      blob: new Blob(["attendee_reference,name\natt-1,Ada Lovelace\n"], {
        type: "text/csv; charset=utf-8",
      }),
      filename: `${dataset}-summit-2026.csv`,
      contentType: "text/csv; charset=utf-8",
    };
  }

  return {
    blob: new Blob(["xlsx-bytes"], {
      type: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    }),
    filename: `${dataset}-summit-2026.xlsx`,
    contentType: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
  };
}

describe("CSV and XLSX exports", () => {
  let clickSpy: ReturnType<typeof vi.spyOn>;

  beforeEach(() => {
    params.eventSlug = "summit-2026";
    clickSpy = vi
      .spyOn(HTMLAnchorElement.prototype, "click")
      .mockImplementation(() => undefined);
    Object.defineProperty(URL, "createObjectURL", {
      configurable: true,
      writable: true,
      value: vi.fn(() => "blob:export"),
    });
    Object.defineProperty(URL, "revokeObjectURL", {
      configurable: true,
      writable: true,
      value: vi.fn(),
    });
    api.exports.download.mockReset().mockImplementation(async (_slug, dataset, format) =>
      downloadedFile(dataset as ExportDataset, format as ExportFormat),
    );
    toast.success.mockReset();
    toast.error.mockReset();
  });

  afterEach(() => {
    clickSpy.mockRestore();
  });

  it("downloads attendee CSV with the backend filename and content type", async () => {
    renderManagement(<ExportsPage />);

    fireEvent.click(screen.getByRole("button", { name: "Download attendees CSV" }));

    await waitFor(() => {
      expect(api.exports.download).toHaveBeenCalledWith(
        "summit-2026",
        "attendees",
        "csv",
        expect.any(AbortSignal),
      );
    });
    const status = await screen.findByRole("status");
    expect(status).toHaveTextContent("attendees-summit-2026.csv");
    expect(status).toHaveTextContent("text/csv; charset=utf-8");
    expect(clickSpy).toHaveBeenCalledTimes(1);
    expect((clickSpy.mock.instances[0] as HTMLAnchorElement).download).toBe(
      "attendees-summit-2026.csv",
    );
    expect(URL.revokeObjectURL).toHaveBeenCalledWith("blob:export");
  });

  it("downloads check-in XLSX with the spreadsheet content type", async () => {
    renderManagement(<ExportsPage />);

    fireEvent.click(screen.getByRole("button", { name: "Download check-ins XLSX" }));

    await waitFor(() => {
      expect(api.exports.download).toHaveBeenCalledWith(
        "summit-2026",
        "checkins",
        "xlsx",
        expect.any(AbortSignal),
      );
    });
    const status = await screen.findByRole("status");
    expect(status).toHaveTextContent("checkins-summit-2026.xlsx");
    expect(status).toHaveTextContent(
      "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    );
    expect((clickSpy.mock.instances[0] as HTMLAnchorElement).download).toBe(
      "checkins-summit-2026.xlsx",
    );
  });

  it("exposes no client-side export filters or datasets", async () => {
    renderManagement(<ExportsPage />);

    expect(screen.getByText(/expose no query filters or parameters/)).toBeInTheDocument();
    expect(screen.queryByRole("textbox")).toBeNull();
    expect(screen.queryByRole("combobox")).toBeNull();
    expect(screen.getAllByRole("button", { name: /^Download (attendees|check-ins) (CSV|XLSX)$/ })).toHaveLength(4);
  });

  it("prevents repeated download requests while one is in flight", async () => {
    let resolveDownload: (value: DownloadedFile) => void = () => undefined;
    api.exports.download.mockImplementationOnce(
      () =>
        new Promise<DownloadedFile>((resolve) => {
          resolveDownload = resolve;
        }),
    );

    renderManagement(<ExportsPage />);

    const csvButton = screen.getByRole("button", { name: "Download attendees CSV" });
    fireEvent.click(csvButton);
    fireEvent.click(csvButton);

    await waitFor(() => {
      expect(api.exports.download).toHaveBeenCalledTimes(1);
      expect(csvButton).toBeDisabled();
      expect(screen.getByRole("button", { name: "Download check-ins XLSX" })).toBeDisabled();
    });

    resolveDownload(downloadedFile("attendees", "csv"));
    await waitFor(() => {
      expect(csvButton).toBeEnabled();
    });
  });

  it.each([
    {
      label: "401",
      error: new ApiError(401, "UNAUTHORIZED", "Sign in again."),
      title: "Authentication required",
      description: "Your session is no longer valid. Sign in again to continue.",
    },
    {
      label: "403",
      error: new ApiError(403, "FORBIDDEN", "Admin access required."),
      title: "Access restricted",
      description: "You do not have permission to manage this event.",
    },
    {
      label: "404",
      error: new ApiError(404, "NOT_FOUND", "Unknown event."),
      title: "Not found",
      description: "Unknown event.",
    },
    {
      label: "422",
      error: new ApiError(422, "VALIDATION_ERROR", "Invalid export request."),
      title: "Invalid request",
      description: "Invalid export request.",
    },
    {
      label: "429",
      error: new ApiError(429, "TOO_MANY_REQUESTS", "Slow down.", [
        { retry_after_seconds: 10 },
      ]),
      title: "Too many requests",
      description: "Please retry in 10 seconds.",
    },
    {
      label: "network",
      error: new Error("Network request failed"),
      title: "Network error",
      description: "Network request failed",
    },
  ])("shows $label export failures", async ({ error, title, description }) => {
    api.exports.download.mockRejectedValueOnce(error);

    renderManagement(<ExportsPage />);

    fireEvent.click(screen.getByRole("button", { name: "Download attendees CSV" }));

    expect(await screen.findByText(title)).toBeInTheDocument();
    expect(screen.getByText(description)).toBeInTheDocument();
    expect(screen.queryByRole("status")).toBeNull();
  });

  it("aborts in-flight downloads and resets state after switching events", async () => {
    let resolveFirstDownload: (value: DownloadedFile) => void = () => undefined;
    api.exports.download
      .mockImplementationOnce(
        () =>
          new Promise<DownloadedFile>((resolve) => {
            resolveFirstDownload = resolve;
          }),
      )
      .mockImplementation(async (_slug, dataset, format) =>
        downloadedFile(dataset as ExportDataset, format as ExportFormat),
      );

    const queryClient = createNoRetryQueryClient();
    const view = renderManagement(
      <QueryClientProvider client={queryClient}>
        <ExportsPage />
      </QueryClientProvider>,
      queryClient,
    );

    fireEvent.click(screen.getByRole("button", { name: "Download attendees CSV" }));
    await waitFor(() => {
      expect(api.exports.download).toHaveBeenCalledTimes(1);
    });
    const firstSignal = api.exports.download.mock.calls[0][3] as AbortSignal;
    expect(firstSignal.aborted).toBe(false);

    params.eventSlug = "other-event";
    view.rerender(
      <QueryClientProvider client={queryClient}>
        <ExportsPage />
      </QueryClientProvider>,
    );

    await waitFor(() => {
      expect(firstSignal.aborted).toBe(true);
    });

    fireEvent.click(screen.getByRole("button", { name: "Download attendees CSV" }));
    await waitFor(() => {
      expect(api.exports.download).toHaveBeenLastCalledWith(
        "other-event",
        "attendees",
        "csv",
        expect.any(AbortSignal),
      );
    });

    resolveFirstDownload(downloadedFile("attendees", "csv"));
  });

  it("exposes accessible, responsive download controls", () => {
    renderManagement(<ExportsPage />);

    expect(screen.getByRole("button", { name: "Download attendees CSV" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Download attendees XLSX" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Download check-ins CSV" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Download check-ins XLSX" })).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: "Download attendees CSV" }).closest(".grid")?.className,
    ).toContain("lg:grid-cols-2");
  });
});
