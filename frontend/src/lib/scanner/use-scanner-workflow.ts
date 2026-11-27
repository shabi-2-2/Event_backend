"use client";

import { useQueryClient } from "@tanstack/react-query";
import { useCallback, useEffect, useReducer, useRef } from "react";
import { useApiClient } from "@/components/providers/api-client-provider";
import { dashboardKeys, managementKeys } from "@/lib/api/query-keys";
import {
  toScannerError,
  unexpectedResponseError,
} from "@/lib/scanner/errors";
import { parseCheckinResponse } from "@/lib/scanner/response";
import {
  createInitialScannerState,
  scannerReducer,
  type ScannerAction,
  type ScannerErrorInfo,
  type ScannerState,
} from "@/lib/scanner/state";

export type ScannerWorkflow = {
  state: ScannerState;
  startCamera: () => void;
  cameraReady: () => void;
  cameraDenied: (error: ScannerErrorInfo) => void;
  cameraUnavailable: (error: ScannerErrorInfo) => void;
  cameraStopped: () => void;
  acceptToken: (token: string, tokenEventSlug?: string) => void;
  confirm: (station: string | null) => Promise<void>;
  reset: () => void;
};

export function useScannerWorkflow(eventSlug: string): ScannerWorkflow {
  const api = useApiClient();
  const queryClient = useQueryClient();
  const [state, dispatch] = useReducer(
    scannerReducer,
    eventSlug,
    createInitialScannerState,
  );
  const stateRef = useRef(state);
  const verifyAbortRef = useRef<AbortController | null>(null);
  const confirmAbortRef = useRef<AbortController | null>(null);
  const verifyingTokenRef = useRef<string | null>(null);
  const confirmingRef = useRef(false);

  const dispatchAction = useCallback((action: ScannerAction) => {
    stateRef.current = scannerReducer(stateRef.current, action);
    dispatch(action);
  }, []);

  const abortRequests = useCallback(() => {
    verifyAbortRef.current?.abort();
    verifyAbortRef.current = null;
    confirmAbortRef.current?.abort();
    confirmAbortRef.current = null;
    verifyingTokenRef.current = null;
    confirmingRef.current = false;
  }, []);

  useEffect(() => {
    abortRequests();
    dispatchAction({ type: "EVENT_CHANGED", eventSlug });
    return abortRequests;
  }, [abortRequests, dispatchAction, eventSlug]);

  const invalidateEventData = useCallback(
    async (slug: string) => {
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: managementKeys.attendeesAll(slug) }),
        queryClient.invalidateQueries({ queryKey: managementKeys.registrationsAll(slug) }),
        queryClient.invalidateQueries({ queryKey: managementKeys.ticketsAll(slug) }),
        queryClient.invalidateQueries({ queryKey: managementKeys.event(slug) }),
        queryClient.invalidateQueries({ queryKey: dashboardKeys.forEvent(slug) }),
      ]);
    },
    [queryClient],
  );

  const startCamera = useCallback(() => {
    dispatchAction({ type: "CAMERA_START", eventSlug });
  }, [dispatchAction, eventSlug]);

  const cameraReady = useCallback(() => {
    dispatchAction({ type: "CAMERA_READY", eventSlug });
  }, [dispatchAction, eventSlug]);

  const cameraDenied = useCallback(
    (error: ScannerErrorInfo) => {
      dispatchAction({ type: "CAMERA_DENIED", eventSlug, error });
    },
    [dispatchAction, eventSlug],
  );

  const cameraUnavailable = useCallback(
    (error: ScannerErrorInfo) => {
      dispatchAction({ type: "CAMERA_UNAVAILABLE", eventSlug, error });
    },
    [dispatchAction, eventSlug],
  );

  const cameraStopped = useCallback(() => {
    dispatchAction({ type: "CAMERA_STOPPED", eventSlug });
  }, [dispatchAction, eventSlug]);

  const acceptToken = useCallback(
    (token: string, tokenEventSlug = eventSlug) => {
      if (
        tokenEventSlug !== eventSlug ||
        verifyingTokenRef.current !== null ||
        confirmingRef.current
      ) {
        return;
      }

      const current = stateRef.current;
      if (
        current.eventSlug !== eventSlug ||
        (current.phase !== "idle" && current.phase !== "scanning")
      ) {
        return;
      }

      verifyingTokenRef.current = token;
      dispatchAction({ type: "TOKEN_ACCEPTED", eventSlug, token });

      const controller = new AbortController();
      verifyAbortRef.current = controller;

      void (async () => {
        try {
          const raw = await api.checkins.verify(
            eventSlug,
            { ticket_token: token },
            controller.signal,
          );
          const response = parseCheckinResponse(raw);
          if (!response) {
            dispatchAction({
              type: "VERIFY_FAILED",
              eventSlug,
              token,
              error: unexpectedResponseError(),
            });
            return;
          }

          dispatchAction({ type: "VERIFY_SUCCEEDED", eventSlug, token, response });
        } catch (error) {
          dispatchAction({
            type: "VERIFY_FAILED",
            eventSlug,
            token,
            error: toScannerError(error),
          });
        } finally {
          if (verifyingTokenRef.current === token) {
            verifyingTokenRef.current = null;
          }
          if (verifyAbortRef.current === controller) {
            verifyAbortRef.current = null;
          }
        }
      })();
    },
    [api, dispatchAction, eventSlug],
  );

  const confirm = useCallback(
    async (station: string | null) => {
      const current = stateRef.current;
      if (current.phase !== "confirmation_required" || confirmingRef.current) {
        return;
      }

      const token = current.token;
      const slug = current.eventSlug;
      confirmingRef.current = true;
      dispatchAction({ type: "CONFIRM_START", eventSlug: slug, token });

      const controller = new AbortController();
      confirmAbortRef.current = controller;

      try {
        const raw = await api.checkins.confirm(
          slug,
          { ticket_token: token, station },
          controller.signal,
        );
        const response = parseCheckinResponse(raw);
        if (!response) {
          dispatchAction({
            type: "CONFIRM_FAILED",
            eventSlug: slug,
            token,
            error: unexpectedResponseError(),
          });
          return;
        }

        dispatchAction({ type: "CONFIRM_SUCCEEDED", eventSlug: slug, token, response });

        if (response.outcome === "checked_in") {
          try {
            await invalidateEventData(slug);
          } catch {
            // The backend result is authoritative even if query refresh fails.
          }
        }
      } catch (error) {
        dispatchAction({
          type: "CONFIRM_FAILED",
          eventSlug: slug,
          token,
          error: toScannerError(error),
        });
      } finally {
        confirmingRef.current = false;
        if (confirmAbortRef.current === controller) {
          confirmAbortRef.current = null;
        }
      }
    },
    [api, dispatchAction, invalidateEventData],
  );

  const reset = useCallback(() => {
    abortRequests();
    dispatchAction({ type: "RESET", eventSlug });
  }, [abortRequests, dispatchAction, eventSlug]);

  return {
    state,
    startCamera,
    cameraReady,
    cameraDenied,
    cameraUnavailable,
    cameraStopped,
    acceptToken,
    confirm,
    reset,
  };
}
