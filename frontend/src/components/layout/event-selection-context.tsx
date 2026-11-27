"use client";

import { usePathname, useRouter, useSearchParams } from "next/navigation";
import {
  createContext,
  useCallback,
  useContext,
  useMemo,
  type ReactNode,
} from "react";

type EventSelectionValue = {
  selectedEventSlug: string | null;
  selectEvent: (slug: string | null) => void;
};

const EventSelectionContext = createContext<EventSelectionValue | null>(null);

export function EventSelectionProvider({ children }: { children: ReactNode }) {
  const router = useRouter();
  const pathname = usePathname();
  const searchParams = useSearchParams();
  const selectedEventSlug = searchParams.get("event");

  const selectEvent = useCallback(
    (slug: string | null) => {
      const params = new URLSearchParams(searchParams.toString());

      if (slug) {
        params.set("event", slug);
      } else {
        params.delete("event");
      }

      const query = params.toString();
      router.replace(`${pathname}${query ? `?${query}` : ""}`, { scroll: false });
    },
    [pathname, router, searchParams],
  );

  const value = useMemo(
    () => ({ selectedEventSlug, selectEvent }),
    [selectedEventSlug, selectEvent],
  );

  return (
    <EventSelectionContext.Provider value={value}>
      {children}
    </EventSelectionContext.Provider>
  );
}

export function useEventSelection(): EventSelectionValue {
  const context = useContext(EventSelectionContext);

  if (!context) {
    throw new Error("useEventSelection must be used within EventSelectionProvider.");
  }

  return context;
}
