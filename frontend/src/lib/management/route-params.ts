"use client";

import { useParams } from "next/navigation";

export function useRouteParam(name: string): string {
  const params = useParams<Record<string, string | string[] | undefined>>();
  const value = params?.[name];

  return Array.isArray(value) ? (value[0] ?? "") : (value ?? "");
}

export function useEventSlugParam(): string {
  return useRouteParam("eventSlug");
}

export function useAttendeeReferenceParam(): string {
  return useRouteParam("attendeeReference");
}

export function useRegistrationReferenceParam(): string {
  return useRouteParam("registrationReference");
}
