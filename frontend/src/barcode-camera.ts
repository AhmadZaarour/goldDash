import type { IScannerControls } from "@zxing/browser";

export function normalizeBarcode(value: string): string | null {
  const code = value.trim();
  return code.length > 0 && code.length <= 50 && !/[\x00-\x1f\x7f]/.test(code)
    ? code
    : null;
}

export function cameraErrorMessage(error: unknown): string {
  const name =
    error && typeof error === "object" && "name" in error
      ? String(error.name)
      : "";
  if (name === "NotAllowedError" || name === "SecurityError")
    return "Allow camera access in Chrome, then try again.";
  if (name === "NotFoundError" || name === "OverconstrainedError")
    return "No camera was found. Choose another camera or enter the barcode manually.";
  if (name === "NotReadableError")
    return "The camera is busy. Close other apps using it, then try again.";
  return "The scanner could not start. Try again or enter the barcode manually.";
}

export async function startBarcodeCamera(
  video: HTMLVideoElement,
  options: {
    signal: AbortSignal;
    deviceId?: string;
    onRead: (barcode: string) => void;
    onInvalid: () => void;
    onInterrupted: () => void;
  },
) {
  const { signal } = options;
  const aborted = () => new DOMException("Camera closed", "AbortError");
  if (signal.aborted) throw aborted();
  // Load the decoder only after the operator opens the scanner.
  const [{ BrowserMultiFormatReader }, library] = await Promise.all([
    import("@zxing/browser"),
    import("@zxing/library"),
  ]);
  if (signal.aborted) throw aborted();
  const { BarcodeFormat, DecodeHintType } = library;
  const reader = new BrowserMultiFormatReader(
    new Map([
      [
        DecodeHintType.POSSIBLE_FORMATS,
        [
          BarcodeFormat.CODE_128,
          BarcodeFormat.CODE_39,
          BarcodeFormat.CODE_93,
          BarcodeFormat.EAN_13,
          BarcodeFormat.EAN_8,
          BarcodeFormat.UPC_A,
          BarcodeFormat.UPC_E,
          BarcodeFormat.ITF,
        ],
      ],
    ]),
    { delayBetweenScanAttempts: 200, delayBetweenScanSuccess: 500 },
  );
  const stream = await navigator.mediaDevices.getUserMedia({
    audio: false,
    video: {
      ...(options.deviceId
        ? { deviceId: { exact: options.deviceId } }
        : { facingMode: { ideal: "environment" } }),
      width: { ideal: 1280 },
      height: { ideal: 720 },
    },
  });
  let controls: IScannerControls | undefined;
  let stopped = false;
  const stop = () => {
    if (stopped) return;
    stopped = true;
    signal.removeEventListener("abort", stop);
    controls?.stop();
    stream.getTracks().forEach((track) => track.stop());
    if (video.srcObject === stream) video.srcObject = null;
  };
  if (signal.aborted) {
    stop();
    throw aborted();
  }
  signal.addEventListener("abort", stop, { once: true });
  stream.getVideoTracks().forEach((track) => {
    track.addEventListener(
      "ended",
      () => {
        if (stopped) return;
        stop();
        options.onInterrupted();
      },
      { once: true },
    );
  });
  try {
    controls = await reader.decodeFromStream(
      stream,
      video,
      (result, error, liveControls) => {
        if (stopped || signal.aborted) return;
        controls = liveControls;
        if (result) {
          const code = normalizeBarcode(result.getText());
          if (!code) {
            options.onInvalid();
            return;
          }
          stop();
          options.onRead(code);
        } else if (
          error &&
          !(
            error instanceof library.NotFoundException ||
            error instanceof library.ChecksumException ||
            error instanceof library.FormatException
          )
        ) {
          stop();
          options.onInterrupted();
        }
      },
    );
    // Closing while video initialization is pending must stop the late decoder too.
    if (stopped || signal.aborted) controls.stop();
    const devices = stopped
      ? []
      : await navigator.mediaDevices.enumerateDevices().catch(() => []);
    return {
      stop,
      deviceId: stream.getVideoTracks()[0]?.getSettings().deviceId || "",
      devices: devices.filter((device) => device.kind === "videoinput"),
    };
  } catch (error) {
    stop();
    throw error;
  }
}
