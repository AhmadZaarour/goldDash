import { useEffect, useRef, useState } from "react";
import { Camera } from "lucide-react";
import { useLanguage } from "./i18n";
import { Modal } from "./ui";
import { cameraErrorMessage, startBarcodeCamera } from "./barcode-camera";

function CameraScanner({ onRead }: { onRead: (barcode: string) => void }) {
  const { t } = useLanguage();
  const video = useRef<HTMLVideoElement>(null);
  const onReadRef = useRef(onRead);
  onReadRef.current = onRead;
  const [attempt, setAttempt] = useState(0);
  const [deviceId, setDeviceId] = useState("");
  const [activeDevice, setActiveDevice] = useState("");
  const [devices, setDevices] = useState<MediaDeviceInfo[]>([]);
  const [phase, setPhase] = useState<"starting" | "ready" | "paused" | "error">(
    "starting",
  );
  const [error, setError] = useState("");
  const [invalid, setInvalid] = useState(false);

  useEffect(() => {
    const controller = new AbortController();
    setError("");
    setInvalid(false);
    setPhase("starting");
    const pause = () => {
      controller.abort();
      setPhase("paused");
    };
    const visibility = () => {
      if (document.hidden) pause();
    };
    document.addEventListener("visibilitychange", visibility);
    window.addEventListener("pagehide", pause);
    async function start() {
      if (document.hidden) {
        pause();
        return;
      }
      if (!window.isSecureContext) {
        setError(
          "Camera scanning requires HTTPS. You can still enter the barcode manually.",
        );
        setPhase("error");
        return;
      }
      if (!navigator.mediaDevices?.getUserMedia) {
        setError(
          "Camera access is unavailable on this device. Enter the barcode manually.",
        );
        setPhase("error");
        return;
      }
      try {
        const session = await startBarcodeCamera(video.current!, {
          signal: controller.signal,
          deviceId,
          onRead: (barcode) => onReadRef.current(barcode),
          onInvalid: () => setInvalid(true),
          onInterrupted: () => {
            controller.abort();
            setError(
              "The camera stopped. Try again or enter the barcode manually.",
            );
            setPhase("error");
          },
        });
        if (controller.signal.aborted) {
          session.stop();
          return;
        }
        setDevices(session.devices);
        setActiveDevice(session.deviceId);
        setPhase("ready");
      } catch (error) {
        if (controller.signal.aborted) return;
        setError(cameraErrorMessage(error));
        setPhase("error");
      }
    }
    void start();
    return () => {
      controller.abort();
      document.removeEventListener("visibilitychange", visibility);
      window.removeEventListener("pagehide", pause);
    };
  }, [deviceId, attempt]);

  return (
    <div className="barcode-camera">
      <p>
        {t(
          "Point the camera at the barcode. Keep the entire barcode visible and well lit.",
        )}
      </p>
      <div className="barcode-camera-preview">
        <video
          key={`${deviceId}-${attempt}`}
          ref={video}
          autoPlay
          muted
          playsInline
          aria-label={t("Camera preview")}
        />
        {(phase === "starting" || phase === "paused") && (
          <span role="status" className="barcode-camera-state">
            {t(
              phase === "starting"
                ? "Starting camera…"
                : "Camera paused. Tap Try again to resume.",
            )}
          </span>
        )}
      </div>
      {devices.length > 1 && (
        <label>
          {t("Camera")}
          <select
            aria-label={t("Camera")}
            value={deviceId || activeDevice}
            disabled={phase === "starting"}
            onChange={(e) => setDeviceId(e.target.value)}
          >
            {devices.map((device, i) => (
              <option key={device.deviceId} value={device.deviceId}>
                {device.label || `${t("Camera")} ${i + 1}`}
              </option>
            ))}
          </select>
        </label>
      )}
      {invalid && (
        <p role="status">
          {t(
            "This barcode is not supported. Try another barcode or enter it manually.",
          )}
        </p>
      )}
      {error && (
        <p role="alert" className="notice error">
          {t(error)}
        </p>
      )}
      {(phase === "error" || phase === "paused") && (
        <button
          type="button"
          className="secondary"
          onClick={() => setAttempt((n) => n + 1)}
        >
          {t("Try again")}
        </button>
      )}
      <p className="muted small">
        {t("The camera closes after one scan. Images stay on your device.")}
      </p>
    </div>
  );
}

export function BarcodeScanButton({
  onScan,
  disabled = false,
}: {
  onScan: (barcode: string) => void;
  disabled?: boolean;
}) {
  const { t } = useLanguage();
  const [open, setOpen] = useState(false);
  return (
    <>
      <button
        type="button"
        className="secondary"
        disabled={disabled}
        onClick={() => setOpen(true)}
      >
        <Camera size={17} />
        {t("Scan barcode")}
      </button>
      {open && (
        <Modal title="Scan barcode" close={() => setOpen(false)}>
          <CameraScanner
            onRead={(barcode) => {
              setOpen(false);
              onScan(barcode);
            }}
          />
        </Modal>
      )}
    </>
  );
}
