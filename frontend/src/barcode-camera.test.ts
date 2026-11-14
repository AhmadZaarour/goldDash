import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import {
  cameraErrorMessage,
  normalizeBarcode,
  startBarcodeCamera,
} from "./barcode-camera";

const mocks = vi.hoisted(() => ({ decode: vi.fn() }));
vi.mock("@zxing/browser", () => ({
  BrowserMultiFormatReader: class {
    decodeFromStream(...args: unknown[]) {
      return mocks.decode(...args);
    }
  },
}));

type ScanCallback = (
  result: { getText: () => string } | undefined,
  error: Error | undefined,
  controls: { stop: () => void },
) => void;

function camera() {
  const stopped = vi.fn();
  const track = {
    stop: stopped,
    addEventListener: vi.fn(),
    getSettings: () => ({ deviceId: "rear" }),
  };
  const stream = {
    getTracks: () => [track],
    getVideoTracks: () => [track],
  } as unknown as MediaStream;
  const getUserMedia = vi.fn().mockResolvedValue(stream);
  vi.stubGlobal("navigator", {
    mediaDevices: {
      getUserMedia,
      enumerateDevices: vi
        .fn()
        .mockResolvedValue([
          { deviceId: "rear", kind: "videoinput", label: "Rear" },
        ]),
    },
  });
  return { stream, stopped, getUserMedia };
}

beforeEach(() => {
  mocks.decode.mockReset();
});
afterEach(() => vi.unstubAllGlobals());

describe("barcode camera", () => {
  it("accepts exact identifiers and rejects empty, oversized or control-character payloads", () => {
    expect(normalizeBarcode(" GI123ABC ")).toBe("GI123ABC");
    expect(normalizeBarcode("REPAIR/1?A&B")).toBe("REPAIR/1?A&B");
    expect(normalizeBarcode("x".repeat(50))).toHaveLength(50);
    for (const invalid of [" ", "x".repeat(51), "ABC\nDEF", "ABC\x00DEF"])
      expect(normalizeBarcode(invalid)).toBeNull();
  });

  it("reads once and releases camera tracks even when the decoder repeats a result", async () => {
    const { stopped, getUserMedia, stream } = camera();
    const controller = new AbortController();
    const controls = { stop: vi.fn() };
    let callback!: ScanCallback;
    mocks.decode.mockImplementation((_stream, video, fn) => {
      video.srcObject = stream;
      callback = fn;
      return Promise.resolve(controls);
    });
    const onRead = vi.fn();
    const session = await startBarcodeCamera(document.createElement("video"), {
      signal: controller.signal,
      onRead,
      onInvalid: vi.fn(),
      onInterrupted: vi.fn(),
    });
    expect(getUserMedia.mock.calls[0][0]).toMatchObject({
      audio: false,
      video: { facingMode: { ideal: "environment" } },
    });
    callback({ getText: () => "GI123ABC" }, undefined, controls);
    callback({ getText: () => "GI123ABC" }, undefined, controls);
    controller.abort();
    session.stop();
    expect(onRead).toHaveBeenCalledExactlyOnceWith("GI123ABC");
    expect(stopped).toHaveBeenCalledTimes(1);
    expect(controls.stop).toHaveBeenCalledTimes(1);
  });

  it("stops a stream granted after the user closes the scanner", async () => {
    const { stopped, getUserMedia, stream } = camera();
    let grant!: (stream: MediaStream) => void;
    getUserMedia.mockImplementation(
      () =>
        new Promise((resolve) => {
          grant = resolve;
        }),
    );
    const controller = new AbortController();
    const pending = startBarcodeCamera(document.createElement("video"), {
      signal: controller.signal,
      onRead: vi.fn(),
      onInvalid: vi.fn(),
      onInterrupted: vi.fn(),
    });
    const rejected = expect(pending).rejects.toMatchObject({
      name: "AbortError",
    });
    await vi.waitFor(() => expect(getUserMedia).toHaveBeenCalled());
    controller.abort();
    grant(stream);
    await rejected;
    expect(stopped).toHaveBeenCalledTimes(1);
    expect(mocks.decode).not.toHaveBeenCalled();
  });

  it("stops decoder initialization that finishes after cancellation", async () => {
    const { stopped, stream } = camera();
    const controller = new AbortController();
    const controls = { stop: vi.fn() };
    let finish!: (controls: { stop: () => void }) => void;
    mocks.decode.mockImplementation((_stream, video) => {
      video.srcObject = stream;
      return new Promise((resolve) => {
        finish = resolve;
      });
    });
    const video = document.createElement("video");
    const pending = startBarcodeCamera(video, {
      signal: controller.signal,
      deviceId: "front",
      onRead: vi.fn(),
      onInvalid: vi.fn(),
      onInterrupted: vi.fn(),
    });
    await vi.waitFor(() => expect(mocks.decode).toHaveBeenCalled());
    controller.abort();
    finish(controls);
    await pending;
    expect(stopped).toHaveBeenCalledTimes(1);
    expect(controls.stop).toHaveBeenCalledTimes(1);
    expect(video.srcObject).toBeNull();
  });

  it("explains denied, missing and busy cameras", () => {
    expect(
      cameraErrorMessage(new DOMException("denied", "NotAllowedError")),
    ).toContain("Allow camera access");
    expect(
      cameraErrorMessage(new DOMException("missing", "NotFoundError")),
    ).toContain("No camera was found");
    expect(
      cameraErrorMessage(new DOMException("busy", "NotReadableError")),
    ).toContain("camera is busy");
  });
});
