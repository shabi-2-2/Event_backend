"use client";

import { Camera, CameraOff, Check, Keyboard, RotateCcw, Square } from "lucide-react";
import { useState, type FormEvent } from "react";
import { ScannerTicketSummary } from "@/components/scanner/scanner-ticket-summary";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { FormField } from "@/components/ui/form-field";
import { Input } from "@/components/ui/input";
import { useEventSlugParam } from "@/lib/management/route-params";
import {
  outcomeTitle,
  outcomeVariant,
  scannerAnnouncement,
} from "@/lib/scanner/outcome";
import {
  isStationValid,
  isTicketTokenValid,
  normalizeStation,
  normalizeTicketToken,
} from "@/lib/scanner/token";
import { useQrCamera } from "@/lib/scanner/use-qr-camera";
import { useScannerWorkflow } from "@/lib/scanner/use-scanner-workflow";

export default function ScannerPage() {
  const eventSlug = useEventSlugParam();

  // Remount on event change so camera tracks, in-flight requests, and all
  // in-memory scan state belong to exactly one event.
  return <ScannerWorkspace key={eventSlug} eventSlug={eventSlug} />;
}

/** No scan history is kept: there is no backend history/detail/undo contract. */
function ScannerWorkspace({ eventSlug }: { eventSlug: string }) {
  const workflow = useScannerWorkflow(eventSlug);
  const { state } = workflow;
  const [manualToken, setManualToken] = useState("");
  const [station, setStation] = useState("");
  const [tokenError, setTokenError] = useState<string | null>(null);
  const [stationError, setStationError] = useState<string | null>(null);

  const {
    videoRef,
    start: startCameraPreview,
    stop: stopCameraPreview,
  } = useQrCamera({
    onReady: workflow.cameraReady,
    onDenied: workflow.cameraDenied,
    onUnavailable: workflow.cameraUnavailable,
    onDetected: (token) => workflow.acceptToken(token, eventSlug),
  });

  const cameraActive =
    state.phase === "requesting_camera" || state.phase === "scanning";

  function clearLocalInputs() {
    setManualToken("");
    setStation("");
    setTokenError(null);
    setStationError(null);
  }

  function handleStartCamera() {
    clearLocalInputs();
    workflow.startCamera();
    void startCameraPreview();
  }

  function handleRetryCamera() {
    clearLocalInputs();
    workflow.reset();
    workflow.startCamera();
    void startCameraPreview();
  }

  function handleStopCamera() {
    stopCameraPreview();
    workflow.cameraStopped();
  }

  function handleReset() {
    stopCameraPreview();
    clearLocalInputs();
    workflow.reset();
  }

  function handleManualTokenSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const token = normalizeTicketToken(manualToken);

    if (!isTicketTokenValid(token)) {
      setTokenError("Enter the complete raw ticket token (20–256 characters).");
      return;
    }

    setTokenError(null);
    setManualToken("");
    stopCameraPreview();
    workflow.cameraStopped();
    workflow.acceptToken(token, eventSlug);
  }

  function handleConfirm() {
    if (!isStationValid(station)) {
      setStationError("Use up to 100 letters, numbers, spaces, or . _ : - characters.");
      return;
    }

    setStationError(null);
    setStation("");
    void workflow.confirm(normalizeStation(station));
  }

  const response = "response" in state ? state.response : null;
  const errorInfo = "error" in state ? state.error : null;
  const isConfirming = state.phase === "confirming";
  const showManualForm =
    state.phase === "idle" ||
    state.phase === "requesting_camera" ||
    state.phase === "scanning" ||
    state.phase === "camera_denied" ||
    state.phase === "camera_unavailable";
  const showOutcomeAlert =
    state.phase === "checked_in" ||
    state.phase === "already_checked_in" ||
    state.phase === "denied";
  const showErrorAlert =
    state.phase === "camera_denied" ||
    state.phase === "camera_unavailable" ||
    state.phase === "request_error";

  return (
    <div className="space-y-6">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-end sm:justify-between">
        <div>
          <p className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
            Event · {eventSlug}
          </p>
          <h1 className="mt-1 text-2xl font-semibold tracking-tight sm:text-3xl">
            QR ticket scanner
          </h1>
          <p className="mt-2 max-w-2xl text-sm text-muted-foreground">
            Verify a ticket, review the backend result, then explicitly confirm check-in.
            Verification never checks anyone in.
          </p>
        </div>
      </div>

      <div className="sr-only" role="status" aria-live="polite" aria-atomic="true">
        {scannerAnnouncement(state)}
      </div>

      <div className="grid items-start gap-6 lg:grid-cols-[minmax(0,1.3fr)_minmax(20rem,0.7fr)]">
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <Camera className="h-4 w-4 text-muted-foreground" aria-hidden="true" />
              Camera
            </CardTitle>
            <CardDescription>
              Start scanning explicitly. The rear camera is preferred where supported.
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="relative aspect-[3/4] w-full overflow-hidden rounded-lg bg-black sm:aspect-video">
              <video
                ref={videoRef}
                autoPlay
                playsInline
                muted
                aria-label="Ticket QR scanner camera preview"
                className={cameraActive ? "h-full w-full object-cover" : "hidden"}
              />
              {!cameraActive ? (
                <div className="absolute inset-0 flex flex-col items-center justify-center gap-2 px-6 text-center text-sm text-white/80">
                  <CameraOff className="h-6 w-6" aria-hidden="true" />
                  <span>
                    {state.phase === "requesting_camera"
                      ? "Requesting camera permission…"
                      : "Camera is off"}
                  </span>
                </div>
              ) : null}
              {cameraActive ? (
                <div
                  className="pointer-events-none absolute inset-[12%] rounded-lg border-2 border-white/70"
                  aria-hidden="true"
                />
              ) : null}
            </div>

            <div className="flex flex-col-reverse gap-2 sm:flex-row">
              {state.phase === "idle" ? (
                <Button type="button" onClick={handleStartCamera} className="w-full sm:w-auto">
                  <Camera className="h-4 w-4" aria-hidden="true" />
                  Start camera
                </Button>
              ) : null}
              {cameraActive ? (
                <Button
                  type="button"
                  variant="outline"
                  onClick={handleStopCamera}
                  className="w-full sm:w-auto"
                >
                  <Square className="h-4 w-4" aria-hidden="true" />
                  Stop camera
                </Button>
              ) : null}
              {showErrorAlert ? (
                <Button
                  type="button"
                  variant="outline"
                  onClick={handleRetryCamera}
                  className="w-full sm:w-auto"
                >
                  <RotateCcw className="h-4 w-4" aria-hidden="true" />
                  Try camera again
                </Button>
              ) : null}
            </div>

            <p className="text-xs leading-5 text-muted-foreground">
              Camera access requires HTTPS or localhost. Use a secure deployment URL, or enter
              the raw ticket token manually below. Raw tokens are never displayed, stored, or
              sent anywhere except the verify and confirm endpoints.
            </p>
          </CardContent>
        </Card>

        <div className="space-y-4">
          {state.phase === "idle" ||
          state.phase === "requesting_camera" ||
          state.phase === "scanning" ? (
            <Card>
              <CardHeader>
                <CardTitle>Verify ticket</CardTitle>
                <CardDescription>
                  Point the camera at a QR code, or paste the raw token it contains.
                </CardDescription>
              </CardHeader>
              <CardContent>
                <p className="text-sm text-muted-foreground">
                  Scanning pauses automatically after one QR code is detected.
                </p>
              </CardContent>
            </Card>
          ) : null}

          {state.phase === "verifying" ? (
            <Alert role="status">
              <AlertTitle>Verifying ticket</AlertTitle>
              <AlertDescription>Checking this ticket with the server.</AlertDescription>
            </Alert>
          ) : null}

          {(state.phase === "confirmation_required" || state.phase === "confirming") &&
          response ? (
            <Card>
              <CardHeader>
                <CardTitle>Confirm check-in</CardTitle>
                <CardDescription>{response.message}</CardDescription>
              </CardHeader>
              <CardContent className="space-y-4">
                {response.ticket ? (
                  <ScannerTicketSummary ticket={response.ticket} />
                ) : null}
                <FormField
                  label="Station (optional)"
                  htmlFor="checkin-station"
                  error={stationError ?? undefined}
                >
                  <Input
                    id="checkin-station"
                    value={station}
                    onChange={(event) => {
                      setStation(event.target.value);
                      setStationError(null);
                    }}
                    maxLength={100}
                    autoComplete="off"
                    placeholder="e.g. Main entrance"
                  />
                </FormField>
                <div className="flex flex-col-reverse gap-2 sm:flex-row sm:justify-end">
                  <Button
                    type="button"
                    variant="outline"
                    onClick={handleReset}
                    disabled={isConfirming}
                    className="w-full sm:w-auto"
                  >
                    Cancel
                  </Button>
                  <Button
                    type="button"
                    onClick={handleConfirm}
                    disabled={isConfirming}
                    className="w-full sm:w-auto"
                  >
                    <Check className="h-4 w-4" aria-hidden="true" />
                    {isConfirming ? "Confirming…" : "Confirm check-in"}
                  </Button>
                </div>
              </CardContent>
            </Card>
          ) : null}

          {state.phase === "confirming" ? (
            <Alert role="status">
              <AlertTitle>Confirming check-in</AlertTitle>
              <AlertDescription>Submitting the explicit confirmation.</AlertDescription>
            </Alert>
          ) : null}

          {showOutcomeAlert && response ? (
            <Alert variant={outcomeVariant(response.outcome)}>
              <AlertTitle>{outcomeTitle(response.outcome)}</AlertTitle>
              <AlertDescription>{response.message}</AlertDescription>
            </Alert>
          ) : null}

          {showErrorAlert && errorInfo ? (
            <Alert variant="destructive">
              <AlertTitle>{errorInfo.title}</AlertTitle>
              <AlertDescription>{errorInfo.description}</AlertDescription>
            </Alert>
          ) : null}

          {showOutcomeAlert && response?.ticket ? (
            <ScannerTicketSummary ticket={response.ticket} />
          ) : null}

          {(showOutcomeAlert || state.phase === "request_error") ? (
            <Button type="button" variant="outline" onClick={handleReset} className="w-full">
              <RotateCcw className="h-4 w-4" aria-hidden="true" />
              Scan next ticket
            </Button>
          ) : null}

          {showManualForm ? (
            <Card>
              <CardHeader>
                <CardTitle className="flex items-center gap-2">
                  <Keyboard className="h-4 w-4 text-muted-foreground" aria-hidden="true" />
                  Manual token entry
                </CardTitle>
                <CardDescription>
                  Use the raw QR payload only. Ticket codes, URLs, and JSON are not accepted.
                </CardDescription>
              </CardHeader>
              <CardContent>
                <form onSubmit={handleManualTokenSubmit} className="space-y-3">
                  <FormField
                    label="Raw ticket token"
                    htmlFor="manual-ticket-token"
                    error={tokenError ?? undefined}
                  >
                    <Input
                      id="manual-ticket-token"
                      type="password"
                      value={manualToken}
                      onChange={(event) => {
                        setManualToken(event.target.value);
                        setTokenError(null);
                      }}
                      autoComplete="off"
                      spellCheck={false}
                      maxLength={256}
                      placeholder="Paste raw token"
                    />
                  </FormField>
                  <Button type="submit" className="w-full">
                    Verify token
                  </Button>
                </form>
              </CardContent>
            </Card>
          ) : null}

          <p className="text-xs text-muted-foreground">
            No recent-scan history is shown because the backend has no scanner history or undo
            endpoint. The active token is held only in memory until confirmation or reset.
          </p>
        </div>
      </div>
    </div>
  );
}
