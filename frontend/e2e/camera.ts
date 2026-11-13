import type { Page } from "@playwright/test";
import codes from "./fixtures/code128.json" with { type: "json" };

declare global {
  interface Window {
    cameraTest: {
      frame: string | null;
      fail: string | null;
      requests: MediaStreamConstraints[];
      stopped: number;
    };
  }
}

export async function camera(
  page: Page,
  frame: string | null = null,
  fail: string | null = null,
) {
  await page.addInitScript(
    ({ codes, frame, fail }) => {
      window.cameraTest = { frame, fail, requests: [], stopped: 0 };
      const devices = ["rear", "front"].map((id) => ({
        kind: "videoinput",
        deviceId: id,
        groupId: "test",
        label: id === "rear" ? "Rear camera" : "Front camera",
        toJSON() {
          return this;
        },
      }));
      Object.defineProperty(navigator, "mediaDevices", {
        configurable: true,
        value: {
          enumerateDevices: async () => devices,
          getUserMedia: async (constraints: MediaStreamConstraints) => {
            window.cameraTest.requests.push(constraints);
            if (window.cameraTest.fail)
              throw new DOMException(
                "Test camera error",
                window.cameraTest.fail,
              );
            const canvas = document.createElement("canvas");
            canvas.width = 1280;
            canvas.height = 720;
            const context = canvas.getContext("2d")!;
            function draw() {
              context.fillStyle = "#fff";
              context.fillRect(0, 0, 1280, 720);
              const pattern =
                codes[window.cameraTest.frame as keyof typeof codes];
              if (!pattern) return;
              const moduleWidth = Math.max(
                1,
                Math.floor(1100 / pattern.reduce((a, b) => a + b, 0)),
              );
              let x =
                (1280 - pattern.reduce((a, b) => a + b, 0) * moduleWidth) / 2;
              pattern.forEach((width, i) => {
                if (i % 2 === 0) {
                  context.fillStyle = "#000";
                  context.fillRect(x, 250, width * moduleWidth, 220);
                }
                x += width * moduleWidth;
              });
            }
            draw();
            const timer = setInterval(draw, 50);
            const stream = canvas.captureStream(15);
            const track = stream.getVideoTracks()[0];
            const originalStop = track.stop.bind(track);
            const deviceId =
              typeof constraints.video === "object" &&
              typeof constraints.video.deviceId === "object"
                ? constraints.video.deviceId.exact
                : "rear";
            Object.defineProperty(track, "getSettings", {
              value: () => ({ deviceId }),
            });
            track.stop = () => {
              window.cameraTest.stopped++;
              clearInterval(timer);
              originalStop();
            };
            return stream;
          },
        },
      });
    },
    { codes, frame, fail },
  );
}

export async function showBarcode(page: Page, code: string | null) {
  await page.evaluate((code) => {
    window.cameraTest.frame = code;
  }, code);
}
