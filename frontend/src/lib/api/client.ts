import type { Page, ListEventsParams, EventRecord } from "@/lib/api/contracts";
import { ApiError } from "@/lib/api/errors";
import { getApiBaseUrl } from "@/lib/env";

export type QueryParamValue =
  | string
  | number
  | boolean
  | null
  | undefined
  | readonly (string | number)[];

export type ApiRequestOptions = {
  method?: "GET" | "POST" | "PATCH" | "DELETE";
  path: string;
  query?: Record<string, QueryParamValue>;
  body?: unknown;
  signal?: AbortSignal;
  headers?: HeadersInit;
  responseType?: "json" | "blob";
};

function appendQueryValue(params: URLSearchParams, key: string, value: QueryParamValue) {
  if (value === null || value === undefined) {
    return;
  }

  if (Array.isArray(value)) {
    value.forEach((item) => params.append(key, String(item)));
    return;
  }

  params.set(key, String(value));
}

export class ApiClient {
  constructor(private readonly getAccessToken: () => Promise<string | null>) {}

  async request<T>(options: ApiRequestOptions): Promise<T> {
    const params = new URLSearchParams();

    Object.entries(options.query ?? {}).forEach(([key, value]) => {
      appendQueryValue(params, key, value);
    });

    const queryString = params.toString();
    const url = `${getApiBaseUrl()}${options.path}${queryString ? `?${queryString}` : ""}`;
    const headers = new Headers(options.headers);
    const token = await this.getAccessToken();

    if (token) {
      headers.set("Authorization", `Bearer ${token}`);
    }

    const hasBody = options.body !== undefined;
    if (hasBody && !(options.body instanceof FormData)) {
      headers.set("Content-Type", "application/json");
    }

    const response = await fetch(url, {
      method: options.method ?? "GET",
      headers,
      body: hasBody ? JSON.stringify(options.body) : undefined,
      signal: options.signal,
      cache: "no-store",
      credentials: "omit",
    });

    if (!response.ok) {
      throw await ApiError.fromResponse(response);
    }

    if (response.status === 204) {
      return undefined as T;
    }

    if (options.responseType === "blob") {
      return (await response.blob()) as T;
    }

    const text = await response.text();
    return (text ? JSON.parse(text) : undefined) as T;
  }

  async download(
    path: string,
    query?: Record<string, QueryParamValue>,
    signal?: AbortSignal,
  ): Promise<Blob> {
    return this.request<Blob>({
      method: "GET",
      path,
      query,
      responseType: "blob",
      signal,
    });
  }

  readonly events = {
    list: (params: ListEventsParams = {}, signal?: AbortSignal) =>
      this.request<Page<EventRecord>>({
        method: "GET",
        path: "/admin/events",
        query: params as Record<string, QueryParamValue>,
        signal,
      }),

    get: (slug: string, signal?: AbortSignal) =>
      this.request<EventRecord>({
        method: "GET",
        path: `/admin/events/${encodeURIComponent(slug)}`,
        signal,
      }),
  };
}
