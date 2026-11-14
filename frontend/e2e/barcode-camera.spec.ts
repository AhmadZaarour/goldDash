import { test, expect, type Page } from "@playwright/test";
import { api, login, navigate } from "./helpers";
import { camera, showBarcode } from "./camera";

const barcode = "GI1234567890ABCDEF";
async function checkout(page: Page) {
  await login(page);
  await navigate(page, "Sales");
  await page
    .getByRole("button", { name: "Customer sale", exact: true })
    .click();
  const sale = page.getByRole("dialog");
  await expect(
    sale.getByRole("button", { name: "Scan barcode", exact: true }),
  ).toBeDisabled();
  await sale.getByLabel("Location", { exact: true }).selectOption("1");
  return sale;
}
const scanner = (page: Page) =>
  page.getByRole("dialog", { name: "Scan barcode", exact: true });

test("sales decode camera frames, preserve scope and avoid duplicate pieces", async ({
  page,
}) => {
  await api(page);
  await camera(page, barcode);
  const lookups: URL[] = [];
  await page.route("**/api/v1/inventory/items?**", async (route) => {
    const url = new URL(route.request().url());
    if (url.searchParams.has("barcode")) {
      lookups.push(url);
      expect(route.request().headers()["x-business-unit"]).toBe("showroom");
    }
    await route.fallback();
  });
  const sale = await checkout(page);
  await sale.getByRole("button", { name: "Scan barcode", exact: true }).click();
  await expect(
    page.getByText("Item added to the sale. Enter its final price.", {
      exact: true,
    }),
  ).toBeVisible();
  await expect(scanner(page)).toHaveCount(0);
  await expect(
    sale.getByLabel("Final price (USD)", { exact: true }),
  ).toHaveValue("");
  expect(lookups).toHaveLength(1);
  expect(lookups[0].searchParams.get("barcode")).toBe(barcode);
  expect(lookups[0].searchParams.get("location_id")).toBe("1");
  expect(lookups[0].searchParams.get("status")).toBe("in_stock");
  await sale.getByRole("button", { name: "Scan barcode", exact: true }).click();
  await expect(
    page.getByText("This item is already in the sale.", { exact: true }),
  ).toBeVisible();
  await expect(
    sale.getByLabel("Final price (USD)", { exact: true }),
  ).toHaveCount(1);
  await expect
    .poll(() => page.evaluate(() => window.cameraTest.stopped))
    .toBeGreaterThanOrEqual(2);
});

test("permission errors can be retried and manual barcode entry stays usable", async ({
  page,
}) => {
  await api(page);
  await camera(page, null, "NotAllowedError");
  const sale = await checkout(page);
  await sale.getByRole("button", { name: "Scan barcode", exact: true }).click();
  await expect(scanner(page).getByRole("alert")).toHaveText(
    "Allow camera access in Chrome, then try again.",
  );
  await page.evaluate(() => {
    window.cameraTest.fail = null;
  });
  await scanner(page)
    .getByRole("button", { name: "Try again", exact: true })
    .click();
  await expect(
    scanner(page).getByLabel("Camera", { exact: true }),
  ).toBeVisible();
  await scanner(page)
    .getByRole("button", { name: "Close", exact: true })
    .click();
  await expect
    .poll(() => page.evaluate(() => window.cameraTest.stopped))
    .toBeGreaterThanOrEqual(1);
  await sale.getByLabel("Scan or enter barcode", { exact: true }).fill(barcode);
  await sale.getByRole("button", { name: "Add", exact: true }).click();
  await expect(
    page.getByText("Item added to the sale. Enter its final price.", {
      exact: true,
    }),
  ).toBeVisible();
});

test("switching cameras releases the previous stream and closing releases the new stream", async ({
  page,
}) => {
  await api(page);
  await camera(page);
  const sale = await checkout(page);
  await sale.getByRole("button", { name: "Scan barcode", exact: true }).click();
  await scanner(page)
    .getByLabel("Camera", { exact: true })
    .selectOption("front");
  await expect
    .poll(() => page.evaluate(() => window.cameraTest.requests.length))
    .toBe(2);
  await expect
    .poll(() => page.evaluate(() => window.cameraTest.stopped))
    .toBeGreaterThanOrEqual(1);
  const constraints = await page.evaluate(() => window.cameraTest.requests[1]);
  expect(constraints.video).toMatchObject({ deviceId: { exact: "front" } });
  await scanner(page)
    .getByRole("button", { name: "Close", exact: true })
    .click();
  await expect
    .poll(() => page.evaluate(() => window.cameraTest.stopped))
    .toBeGreaterThanOrEqual(2);
});

test("a barcode absent from the selected inventory is not added", async ({
  page,
}) => {
  await api(page);
  await camera(page, "MISSING-ITEM");
  await page.route("**/api/v1/inventory/items?**", async (route) => {
    if (new URL(route.request().url()).searchParams.has("barcode"))
      return route.fulfill({ json: [], headers: { "X-Total-Count": "0" } });
    await route.fallback();
  });
  const sale = await checkout(page);
  await sale.getByRole("button", { name: "Scan barcode", exact: true }).click();
  await expect(scanner(page)).toHaveCount(0);
  await expect(sale.getByRole("alert")).toContainText(
    "The item was not found at this location.",
  );
  await expect(sale.getByLabel("Product", { exact: true })).toHaveValue("");
});

test("service checkout scans the job and posts the entered amount", async ({
  page,
}) => {
  await api(page, "cashier");
  await camera(page, "REPAIR/001");
  const service = {
    id: 1,
    barcode: "REPAIR/001",
    status: "finished",
    notes: "Polished",
    cost: "0",
    sale: null,
  };
  let payment: Record<string, unknown> | undefined;
  await page.route("**/api/v1/servicing**", async (route) => {
    if (route.request().method() === "POST") {
      payment = route.request().postDataJSON();
      expect(route.request().headers()["idempotency-key"]).toBeTruthy();
      expect(route.request().headers()["x-business-unit"]).toBe("showroom");
      return route.fulfill({
        status: 201,
        json: { id: 1, barcode: service.barcode, amount_usd: payment!.cost },
      });
    }
    return route.fulfill({ json: [service] });
  });
  await login(page);
  await navigate(page, "Sales");
  await page.getByRole("button", { name: "Service sale", exact: true }).click();
  const form = page.getByRole("dialog", { name: "Service sale", exact: true });
  await form.getByLabel("Cost (USD)", { exact: true }).fill("12.50");
  await form.getByRole("button", { name: "Scan barcode", exact: true }).click();
  await expect(scanner(page)).toHaveCount(0);
  await expect(form.getByText("Polished", { exact: true })).toBeVisible();
  await expect(form.getByLabel("Cost (USD)", { exact: true })).toHaveValue(
    "12.50",
  );
  await form
    .getByRole("button", { name: "Submit payment", exact: true })
    .click();
  await expect(form).toHaveCount(0);
  expect(payment).toEqual({
    barcode: "REPAIR/001",
    location_id: 1,
    cost: "12.50",
  });
  await expect(page.getByRole("status")).toContainText(
    "Service payment recorded",
  );
});

test("scanner rejects an oversized barcode and shows translated controls", async ({
  page,
}) => {
  await api(page);
  await camera(page, "X".repeat(51));
  await login(page);
  await navigate(page, "Servicing");
  await page.getByRole("button", { name: "Scan barcode", exact: true }).click();
  await expect(scanner(page).getByRole("status")).toContainText(
    "This barcode is not supported.",
  );
  await showBarcode(page, null);
  await scanner(page)
    .getByRole("button", { name: "Close", exact: true })
    .click();
  await page.getByRole("button", { name: "العربية", exact: true }).click();
  await page.getByRole("button", { name: "مسح الباركود", exact: true }).click();
  await expect(
    page
      .getByRole("dialog")
      .getByRole("heading", { name: "مسح الباركود", exact: true }),
  ).toBeVisible();
});

test("backgrounding pauses capture until the operator resumes", async ({
  page,
}) => {
  await api(page);
  await camera(page);
  const sale = await checkout(page);
  await sale.getByRole("button", { name: "Scan barcode", exact: true }).click();
  await expect(
    scanner(page).getByLabel("Camera", { exact: true }),
  ).toBeVisible();
  await page.evaluate(() => {
    Object.defineProperty(document, "hidden", {
      configurable: true,
      value: true,
    });
    document.dispatchEvent(new Event("visibilitychange"));
  });
  await expect(scanner(page).getByRole("status")).toHaveText(
    "Camera paused. Tap Try again to resume.",
  );
  await expect
    .poll(() => page.evaluate(() => window.cameraTest.stopped))
    .toBeGreaterThanOrEqual(1);
  await page.evaluate(() => {
    Object.defineProperty(document, "hidden", {
      configurable: true,
      value: false,
    });
    document.dispatchEvent(new Event("visibilitychange"));
  });
  expect(await page.evaluate(() => window.cameraTest.requests.length)).toBe(1);
  await showBarcode(page, barcode);
  await scanner(page)
    .getByRole("button", { name: "Try again", exact: true })
    .click();
  await expect(
    page.getByText("Item added to the sale. Enter its final price.", {
      exact: true,
    }),
  ).toBeVisible();
});

test("insecure camera access explains HTTPS while manual checkout still works", async ({
  page,
}) => {
  await api(page);
  await camera(page);
  await page.addInitScript(() => {
    Object.defineProperty(window, "isSecureContext", {
      configurable: true,
      value: false,
    });
  });
  const sale = await checkout(page);
  await sale.getByRole("button", { name: "Scan barcode", exact: true }).click();
  await expect(scanner(page).getByRole("alert")).toHaveText(
    "Camera scanning requires HTTPS. You can still enter the barcode manually.",
  );
  expect(await page.evaluate(() => window.cameraTest.requests.length)).toBe(0);
  await scanner(page)
    .getByRole("button", { name: "Close", exact: true })
    .click();
  await sale.getByLabel("Scan or enter barcode", { exact: true }).fill(barcode);
  await sale.getByRole("button", { name: "Add", exact: true }).click();
  await expect(
    page.getByText("Item added to the sale. Enter its final price.", {
      exact: true,
    }),
  ).toBeVisible();
});

test("unknown service scanning reports an error and intake has no manual barcode", async ({
  page,
}) => {
  await api(page, "employee");
  await camera(page, "REPAIR/001");
  await login(page);
  await navigate(page, "Servicing");
  await page.getByRole("button", { name: "Scan barcode", exact: true }).click();
  await expect(page.getByRole("alert")).toContainText("Service not found");
  await page.getByRole("button", { name: "New service", exact: true }).click();
  const form = page.getByRole("dialog", { name: "New service", exact: true });
  await expect(form.getByLabel("Barcode", { exact: true })).toHaveCount(0);
  await expect(form.getByLabel("Status", { exact: true })).toHaveValue(
    "in_progress",
  );
});
