import type {
  AnalyticsDateRangeParams,
  AttendanceAnalyticsResponse,
  AttendeeListParams,
  AttendeeRecord,
  CheckinResponse,
  ConfirmCheckinRequest,
  EmailAnalyticsResponse,
  EventCreateRequest,
  EventRecord,
  EventUpdateRequest,
  ListEventsParams,
  OverviewAnalyticsResponse,
  Page,
  RegistrationAnalyticsResponse,
  RegistrationListParams,
  RegistrationRecord,
  StaffCreateRequest,
  StaffListParams,
  StaffRecord,
  StaffRoleUpdateRequest,
  TicketCheckRequest,
  TicketListParams,
  TicketRecord,
  TicketResendResponse,
} from "@/lib/api/contracts";
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

    create: (body: EventCreateRequest, signal?: AbortSignal) =>
      this.request<EventRecord>({
        method: "POST",
        path: "/admin/events",
        body,
        signal,
      }),

    update: (slug: string, body: EventUpdateRequest, signal?: AbortSignal) =>
      this.request<EventRecord>({
        method: "PATCH",
        path: `/admin/events/${encodeURIComponent(slug)}`,
        body,
        signal,
      }),

    publish: (slug: string, signal?: AbortSignal) =>
      this.request<EventRecord>({
        method: "POST",
        path: `/admin/events/${encodeURIComponent(slug)}/publish`,
        signal,
      }),

    archive: (slug: string, signal?: AbortSignal) =>
      this.request<EventRecord>({
        method: "POST",
        path: `/admin/events/${encodeURIComponent(slug)}/archive`,
        signal,
      }),
  };

  readonly analytics = {
    overview: (slug: string, signal?: AbortSignal) =>
      this.request<OverviewAnalyticsResponse>({
        method: "GET",
        path: `/admin/events/${encodeURIComponent(slug)}/analytics/overview`,
        signal,
      }),

    registrations: (
      slug: string,
      range: AnalyticsDateRangeParams = {},
      signal?: AbortSignal,
    ) =>
      this.request<RegistrationAnalyticsResponse>({
        method: "GET",
        path: `/admin/events/${encodeURIComponent(slug)}/analytics/registrations`,
        query: {
          from_date: range.from_date,
          to_date: range.to_date,
        },
        signal,
      }),

    attendance: (
      slug: string,
      range: AnalyticsDateRangeParams = {},
      signal?: AbortSignal,
    ) =>
      this.request<AttendanceAnalyticsResponse>({
        method: "GET",
        path: `/admin/events/${encodeURIComponent(slug)}/analytics/attendance`,
        query: {
          from_date: range.from_date,
          to_date: range.to_date,
        },
        signal,
      }),

    emailDeliveries: (slug: string, signal?: AbortSignal) =>
      this.request<EmailAnalyticsResponse>({
        method: "GET",
        path: `/admin/events/${encodeURIComponent(slug)}/analytics/email-deliveries`,
        signal,
      }),
  };

  readonly attendees = {
    list: (slug: string, params: AttendeeListParams = {}, signal?: AbortSignal) =>
      this.request<Page<AttendeeRecord>>({
        method: "GET",
        path: `/admin/events/${encodeURIComponent(slug)}/attendees`,
        query: params as Record<string, QueryParamValue>,
        signal,
      }),

    get: (slug: string, attendeeReference: string, signal?: AbortSignal) =>
      this.request<AttendeeRecord>({
        method: "GET",
        path: `/admin/events/${encodeURIComponent(slug)}/attendees/${encodeURIComponent(attendeeReference)}`,
        signal,
      }),
  };

  readonly registrations = {
    list: (slug: string, params: RegistrationListParams = {}, signal?: AbortSignal) =>
      this.request<Page<RegistrationRecord>>({
        method: "GET",
        path: `/admin/events/${encodeURIComponent(slug)}/registrations`,
        query: params as Record<string, QueryParamValue>,
        signal,
      }),

    get: (slug: string, registrationReference: string, signal?: AbortSignal) =>
      this.request<RegistrationRecord>({
        method: "GET",
        path: `/admin/events/${encodeURIComponent(slug)}/registrations/${encodeURIComponent(registrationReference)}`,
        signal,
      }),

    cancel: (slug: string, registrationReference: string, signal?: AbortSignal) =>
      this.request<RegistrationRecord>({
        method: "POST",
        path: `/admin/events/${encodeURIComponent(slug)}/registrations/${encodeURIComponent(registrationReference)}/cancel`,
        signal,
      }),
  };

  readonly tickets = {
    list: (slug: string, params: TicketListParams = {}, signal?: AbortSignal) =>
      this.request<Page<TicketRecord>>({
        method: "GET",
        path: `/admin/events/${encodeURIComponent(slug)}/tickets`,
        query: params as Record<string, QueryParamValue>,
        signal,
      }),

    revoke: (slug: string, ticketReference: string, signal?: AbortSignal) =>
      this.request<TicketRecord>({
        method: "POST",
        path: `/admin/events/${encodeURIComponent(slug)}/tickets/${encodeURIComponent(ticketReference)}/revoke`,
        signal,
      }),

    resend: (slug: string, ticketReference: string, signal?: AbortSignal) =>
      this.request<TicketResendResponse>({
        method: "POST",
        path: `/admin/events/${encodeURIComponent(slug)}/tickets/${encodeURIComponent(ticketReference)}/resend`,
        signal,
      }),
  };

  readonly checkins = {
    verify: (eventSlug: string, body: TicketCheckRequest, signal?: AbortSignal) =>
      this.request<CheckinResponse>({
        method: "POST",
        path: `/events/${encodeURIComponent(eventSlug)}/checkins/verify`,
        body,
        signal,
      }),

    confirm: (eventSlug: string, body: ConfirmCheckinRequest, signal?: AbortSignal) =>
      this.request<CheckinResponse>({
        method: "POST",
        path: `/events/${encodeURIComponent(eventSlug)}/checkins/confirm`,
        body,
        signal,
      }),
  };

  readonly staff = {
    list: (slug: string, params: StaffListParams = {}, signal?: AbortSignal) =>
      this.request<Page<StaffRecord>>({
        method: "GET",
        path: `/admin/events/${encodeURIComponent(slug)}/staff`,
        query: params as Record<string, QueryParamValue>,
        signal,
      }),

    create: (slug: string, body: StaffCreateRequest, signal?: AbortSignal) =>
      this.request<StaffRecord>({
        method: "POST",
        path: `/admin/events/${encodeURIComponent(slug)}/staff`,
        body,
        signal,
      }),

    updateRole: (
      slug: string,
      userId: string,
      body: StaffRoleUpdateRequest,
      signal?: AbortSignal,
    ) =>
      this.request<StaffRecord>({
        method: "PATCH",
        path: `/admin/events/${encodeURIComponent(slug)}/staff/${encodeURIComponent(userId)}`,
        body,
        signal,
      }),

    remove: (slug: string, userId: string, signal?: AbortSignal) =>
      this.request<void>({
        method: "DELETE",
        path: `/admin/events/${encodeURIComponent(slug)}/staff/${encodeURIComponent(userId)}`,
        signal,
      }),
  };
}
