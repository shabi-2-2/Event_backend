import type { DownloadedFile } from "@/lib/api/client";

/** Removes path segments from a backend-provided filename before saving. */
export function safeDownloadFilename(value: string, fallback = "download"): string {
  const base = value.trim().split(/[/\\]/).pop() ?? "";
  return base && base !== "." && base !== ".." ? base : fallback;
}

/** Saves a backend-generated blob using the backend's Content-Disposition name. */
export function triggerBrowserDownload(file: DownloadedFile): void {
  const url = URL.createObjectURL(file.blob);
  const anchor = document.createElement("a");

  anchor.href = url;
  anchor.download = safeDownloadFilename(file.filename);
  anchor.style.display = "none";
  document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();
  URL.revokeObjectURL(url);
}
