import { afterEach, describe, expect, it, vi } from "vitest";
import { Operation, request, renew, clearSession } from "./api";
const json = (data: unknown, status = 200) =>
  new Response(JSON.stringify(data), {
    status,
    headers: { "Content-Type": "application/json" },
  });
afterEach(() => {
  clearSession();
  vi.unstubAllGlobals();
});
describe("API operations", () => {
  it("retains the same retry key after an uncertain response and resets it after success", async () => {
    const fetcher = vi
      .fn()
      .mockRejectedValueOnce(new TypeError("offline"))
      .mockResolvedValue(json({ id: 1 }));
    vi.stubGlobal("fetch", fetcher);
    const op = new Operation();
    await expect(
      op.send("/purchases/item", { weight: "1" }, "POST", true),
    ).rejects.toThrow("offline");
    await op.send("/purchases/item", { weight: "1" }, "POST", true);
    const key = (n: number) =>
      (fetcher.mock.calls[n][1].headers as Headers).get("Idempotency-Key");
    expect(key(0)).toBeTruthy();
    expect(key(0)).toBe(key(1));
    fetcher.mockResolvedValue(json({ id: 2 }));
    await op.send("/purchases/item", { weight: "1" }, "POST", true);
    expect(key(2)).not.toBe(key(1));
  });
  it("rotates a refresh token only once for concurrent expired requests", async () => {
    sessionStorage.setItem("gold-refresh", "old");
    let refreshes = 0;
    const fetcher = vi.fn(async (url: string, init: RequestInit) => {
      if (url.endsWith("/auth/refresh")) {
        refreshes++;
        return json({
          access_token: "new-access",
          refresh_token: "new-refresh",
        });
      }
      return (init.headers as Headers).get("Authorization") ===
        "Bearer new-access"
        ? json({ id: 1 })
        : json({ detail: "expired" }, 401);
    });
    vi.stubGlobal("fetch", fetcher);
    const result = await Promise.all([
      request("/products"),
      request("/customers"),
    ]);
    expect(result).toEqual([{ id: 1 }, { id: 1 }]);
    expect(refreshes).toBe(1);
    expect(sessionStorage.getItem("gold-refresh")).toBe("new-refresh");
  });
  it("clears rejected refresh credentials", async () => {
    sessionStorage.setItem("gold-refresh", "expired");
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(json({ detail: "invalid" }, 401)),
    );
    expect(await renew()).toBe(false);
    expect(sessionStorage.getItem("gold-refresh")).toBeNull();
  });
  it("does not change a photo upload content type", async () => {
    const fetcher = vi.fn().mockResolvedValue(json({ id: 1 }));
    vi.stubGlobal("fetch", fetcher);
    await request("/inventory/items/1/photo", {
      method: "POST",
      body: new Blob(["image"]),
      headers: { "Content-Type": "image/jpeg" },
    });
    expect(
      (fetcher.mock.calls[0][1].headers as Headers).get("Content-Type"),
    ).toBe("image/jpeg");
  });
});

it("keeps an uncertain operation key when a form is edited and restored", async () => {
  const fetcher = vi.fn().mockRejectedValue(new TypeError("offline"));
  vi.stubGlobal("fetch", fetcher);
  const op = new Operation();
  await expect(
    op.send("/purchases/item", { weight: "1" }, "POST", true),
  ).rejects.toThrow();
  await expect(
    op.send("/purchases/item", { weight: "2" }, "POST", true),
  ).rejects.toThrow();
  fetcher.mockResolvedValue(json({ id: 1 }));
  await op.send("/purchases/item", { weight: "1" }, "POST", true);
  const key = (n: number) =>
    (fetcher.mock.calls[n][1].headers as Headers).get("Idempotency-Key");
  expect(key(0)).toBe(key(2));
  expect(key(1)).not.toBe(key(0));
});
