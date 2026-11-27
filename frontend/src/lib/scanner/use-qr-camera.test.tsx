import { act, renderHook } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { useQrCamera } from "@/lib/scanner/use-qr-camera";

const TOKEN = "raw-ticket-token-1234567890";

const zxing = vi.hoisted(() => ({
  stop: vi.fn(),
  decodeFromStream: vi.fn(),
}));

vi.mock("@zxing/browser", () => ({
  BrowserQRCodeReader: class {
    decodeFromStream(...args: unknown[]) {
      return zxing.decodeFromStream(...args);
    }
  },
}));

const originalMediaDevices = Object.getOwnPropertyDescriptor(navigator, "mediaDevices");
const originalSecureContext = Object.getOwnPropertyDescriptor(window, "isSecureContext");

function setSecureContext(value: boolean) {
  Object.defineProperty(window, "isSecureContext", {
    configurable: true,
    value,
  });
}

function setMediaDevices(getUserMedia: unknown) {
  Object.defineProperty(navigator, "mediaDevices", {
    configurable: true,
    value: getUserMedia ? { getUserMedia } : undefined,
  });
}

function callbacks() {
  return {
    onReady: vi.fn(),
    onDenied: vi.fn(),
    onUnavailable: vi.fn(),
    onDetected: vi.fn(),
  };
}

describe("useQrCamera", () => {
  let track: MediaStreamTrack;
  let stream: MediaStream;
  let getUserMedia: ReturnType<typeof vi.fn>;

  beforeEach(() => {
    setSecureContext(true);
    zxing.stop.mockReset();
    zxing.decodeFromStream.mockReset();
    zxing.stop.mockImplementation(() => undefined);
    zxing.decodeFromStream.mockResolvedValue({ stop: zxing.stop });

    track = { stop: vi.fn() } as unknown as MediaStreamTrack;
    stream = { getTracks: () => [track] } as unknown as MediaStream;
    getUserMedia = vi.fn().mockResolvedValue(stream);
    setMediaDevices(getUserMedia);
  });

  afterEach(() => {
    if (originalMediaDevices) {
      Object.defineProperty(navigator, "mediaDevices", originalMediaDevices);
    } else {
      Reflect.deleteProperty(navigator, "mediaDevices");
    }
    if (originalSecureContext) {
      Object.defineProperty(window, "isSecureContext", originalSecureContext);
    } else {
      Reflect.deleteProperty(window, "isSecureContext");
    }
  });

  it("requests the rear camera only after start and decodes with ZXing", async () => {
    const handlers = callbacks();
    const { result } = renderHook(() => useQrCamera(handlers));

    await act(async () => {
      await result.current.start();
    });

    expect(getUserMedia).toHaveBeenCalledWith({
      audio: false,
      video: { facingMode: { ideal: "environment" } },
    });
    expect(zxing.decodeFromStream).toHaveBeenCalledWith(
      stream,
      undefined,
      expect.any(Function),
    );
    expect(handlers.onReady).toHaveBeenCalledTimes(1);
  });

  it("pauses decoding and reports one token only once", async () => {
    const handlers = callbacks();
    const { result } = renderHook(() => useQrCamera(handlers));

    await act(async () => {
      await result.current.start();
    });

    const decode = zxing.decodeFromStream.mock.calls[0][2] as (result?: {
      getText: () => string;
    }) => void;

    act(() => {
      decode({ getText: () => TOKEN });
      decode({ getText: () => TOKEN });
      decode({ getText: () => "second-token-1234567890" });
    });

    expect(handlers.onDetected).toHaveBeenCalledTimes(1);
    expect(handlers.onDetected).toHaveBeenCalledWith(TOKEN);
    expect(zxing.stop).toHaveBeenCalledTimes(1);
    expect(track.stop).toHaveBeenCalledTimes(1);
  });

  it("maps permission denial and unavailable cameras to distinct states", async () => {
    const deniedHandlers = callbacks();
    getUserMedia.mockRejectedValueOnce(new DOMException("blocked", "NotAllowedError"));
    const denied = renderHook(() => useQrCamera(deniedHandlers));

    await act(async () => {
      await denied.result.current.start();
    });

    expect(deniedHandlers.onDenied).toHaveBeenCalledWith(
      expect.objectContaining({ title: "Camera permission denied" }),
    );

    const unavailableHandlers = callbacks();
    getUserMedia.mockRejectedValueOnce(new DOMException("missing", "NotFoundError"));
    const unavailable = renderHook(() => useQrCamera(unavailableHandlers));

    await act(async () => {
      await unavailable.result.current.start();
    });

    expect(unavailableHandlers.onUnavailable).toHaveBeenCalledWith(
      expect.objectContaining({ title: "Camera unavailable" }),
    );
  });

  it("explains insecure contexts without calling getUserMedia", async () => {
    setSecureContext(false);
    const handlers = callbacks();
    const { result } = renderHook(() => useQrCamera(handlers));

    await act(async () => {
      await result.current.start();
    });

    expect(getUserMedia).not.toHaveBeenCalled();
    expect(handlers.onUnavailable).toHaveBeenCalledWith(
      expect.objectContaining({ title: "Secure connection required" }),
    );
  });

  it("releases scanner controls and media tracks on stop", async () => {
    const handlers = callbacks();
    const { result } = renderHook(() => useQrCamera(handlers));

    await act(async () => {
      await result.current.start();
    });

    act(() => {
      result.current.stop();
    });

    expect(zxing.stop).toHaveBeenCalledTimes(1);
    expect(track.stop).toHaveBeenCalledTimes(1);
  });
});
