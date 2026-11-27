"use client";

import { useCallback, useEffect, useRef, type RefObject } from "react";
import type { IScannerControls } from "@zxing/browser";
import {
  insecureContextError,
  toCameraError,
} from "@/lib/scanner/errors";
import type { ScannerErrorInfo } from "@/lib/scanner/state";

type QrCameraCallbacks = {
  onReady: () => void;
  onDenied: (error: ScannerErrorInfo) => void;
  onUnavailable: (error: ScannerErrorInfo) => void;
  onDetected: (token: string) => void;
};

export type QrCamera = {
  videoRef: RefObject<HTMLVideoElement | null>;
  start: () => Promise<void>;
  stop: () => void;
};

function isPermissionDenied(error: unknown): boolean {
  return (
    error instanceof DOMException &&
    (error.name === "NotAllowedError" || error.name === "SecurityError")
  );
}

function stopTracks(stream: MediaStream | null): void {
  stream?.getTracks().forEach((track) => track.stop());
}

export function useQrCamera(callbacks: QrCameraCallbacks): QrCamera {
  const videoRef = useRef<HTMLVideoElement>(null);
  const controlsRef = useRef<IScannerControls | null>(null);
  const streamRef = useRef<MediaStream | null>(null);
  const generationRef = useRef(0);
  const detectedTokenRef = useRef<string | null>(null);
  const callbacksRef = useRef(callbacks);

  useEffect(() => {
    callbacksRef.current = callbacks;
  }, [callbacks]);

  const stopCamera = useCallback((clearDetection = true) => {
    generationRef.current += 1;

    const controls = controlsRef.current;
    controlsRef.current = null;
    try {
      controls?.stop();
    } catch {
      // Cleanup must continue even if a browser's scanner controls fail to stop.
    }

    const stream = streamRef.current;
    streamRef.current = null;
    stopTracks(stream);

    const video = videoRef.current;
    if (video) {
      video.srcObject = null;
    }

    if (clearDetection) {
      detectedTokenRef.current = null;
    }
  }, []);

  useEffect(() => () => stopCamera(true), [stopCamera]);

  const start = useCallback(async () => {
    stopCamera(true);
    const generation = generationRef.current;

    const finishUnavailable = (error: ScannerErrorInfo) => {
      if (generation === generationRef.current) {
        callbacksRef.current.onUnavailable(error);
      }
    };

    if (typeof window === "undefined" || !window.isSecureContext) {
      finishUnavailable(insecureContextError());
      return;
    }

    const mediaDevices = navigator.mediaDevices;
    if (!mediaDevices?.getUserMedia) {
      finishUnavailable(insecureContextError());
      return;
    }

    let stream: MediaStream | null = null;

    try {
      stream = await mediaDevices.getUserMedia({
        audio: false,
        video: { facingMode: { ideal: "environment" } },
      });

      if (generation !== generationRef.current) {
        stopTracks(stream);
        return;
      }

      const { BrowserQRCodeReader } = await import("@zxing/browser");
      const reader = new BrowserQRCodeReader();

      const controls = await reader.decodeFromStream(
        stream,
        videoRef.current ?? undefined,
        (result) => {
          if (generation !== generationRef.current) {
            return;
          }

          const text = result?.getText?.()?.trim();
          if (!text || detectedTokenRef.current === text) {
            return;
          }

          // Pause decoding before any network work so one QR cannot enqueue
          // duplicate verification requests.
          detectedTokenRef.current = text;
          stopCamera(false);
          callbacksRef.current.onDetected(text);
        },
      );

      if (generation !== generationRef.current) {
        try {
          controls.stop();
        } catch {
          // The stale camera generation is already being cleaned up.
        }
        stopTracks(stream);
        return;
      }

      controlsRef.current = controls;
      streamRef.current = stream;
      callbacksRef.current.onReady();
    } catch (error) {
      stopTracks(stream);
      if (generation !== generationRef.current) {
        return;
      }

      if (isPermissionDenied(error)) {
        callbacksRef.current.onDenied(toCameraError(error));
      } else {
        callbacksRef.current.onUnavailable(toCameraError(error));
      }
    }
  }, [stopCamera]);

  const stop = useCallback(() => stopCamera(true), [stopCamera]);

  return { videoRef, start, stop };
}
