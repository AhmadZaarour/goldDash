import { test, expect, type Page } from "@playwright/test";
async function api(page: Page, role = "admin") {
  const user = { id: 1, username: "Ahmad", email: "owner@example.com", role };
  await page.route("**/api/v1/**", async (route) => {
    const req = route.request();
    const url = new URL(req.url());
    const path = url.pathname.replace("/api/v1", "");
    let body: unknown = [];
    if (path === "/auth/login" || path === "/auth/refresh")
      body = { access_token: "test-token", refresh_token: "test-refresh" };
    else if (path === "/auth/me") body = user;
    else if (path === "/development/reset-status") body = { enabled: false };
    else if (path === "/insights/monthly-profit")
      body = {
        month: url.searchParams.get("month"),
        timezone: "Asia/Beirut",
        customer_sales_count: 3,
        returned_items_count: 1,
        sales_usd: "500.00",
        refunds_usd: "50.00",
        net_sales_usd: "450.00",
        gold_value_usd: "300.00",
        making_cost_usd: "15.00",
        restored_cost_usd: "30.00",
        net_cost_usd: "285.00",
        gross_profit_usd: "165.00",
        expenses_usd: "25.00",
        net_profit_usd: "140.00",
        supplier_sales: [
          {
            purity_id: 1,
            weight_grams: "2.500",
            settlement_grams: "2.600",
            making_usd: "10.00",
          },
        ],
        supplier_purchases: [],
      };
    else if (path === "/inventory/items")
      body = [
        {
          id: 1,
          barcode: "GI1234567890ABCDEF",
          product_name: "Classic gold ring",
          sku: "RING-01",
          product_id: 1,
          category_id: 1,
          purity_id: 1,
          weight: "2.500",
          status: "in_stock",
          location_id: 1,
          purchase_item_id: 1,
          image_url: null,
        },
      ];
    else if (path === "/suppliers")
      body = [
        { id: 1, name: "Gold supplier", phone: "12345", is_active: true },
      ];
    else if (path === "/locations")
      body = [{ id: 1, name: "Main showroom", code: "MAIN", is_active: true }];
    else if (path === "/products")
      body = [
        {
          id: 1,
          name: "Classic gold ring",
          sku: "RING-01",
          inventory_type: "item",
          category_id: 1,
          purity_id: 1,
        },
      ];
    else if (path === "/goldpurities")
      body = [{ id: 1, name: "22K", karat: 22, purity: 91.6 }];
    else if (path === "/categories") body = [{ id: 1, name: "Rings" }];
    else if (path === "/cash/summary")
      body = {
        net_usd: "125.00",
        received_usd: "200.00",
        refunded_usd: "0",
        expenses_usd: "25.00",
        withdrawals_usd: "50.00",
        supplier_sent_usd: "0",
        supplier_received_usd: "0",
      };
    else if (path === "/purchases/item" && req.method() === "POST")
      body = {
        id: 1,
        invoice_number: "INV-1",
        location_id: 1,
        created_at: new Date().toISOString(),
      };
    const rows = Array.isArray(body) ? body.length : 0;
    await route.fulfill({
      json: body,
      headers: { "X-Total-Count": String(rows) },
    });
  });
}
async function login(page: Page) {
  await page.goto("/");
  await page.getByLabel("Email", { exact: true }).fill("owner@example.com");
  await page.getByLabel("Password", { exact: true }).fill("TestPassword123!");
  await page.getByRole("button", { name: "Sign in", exact: true }).click();
  await expect(
    page.getByRole("heading", { name: "Overview", exact: true }),
  ).toBeVisible();
}
async function navigate(page: Page, label: string) {
  const menu = page.getByRole("button", { name: "Menu", exact: true });
  if (await menu.isVisible()) await menu.click();
  await page
    .locator("nav")
    .getByRole("link", { name: label, exact: true })
    .click();
}
test("login, inventory, Arabic RTL and mobile navigation", async ({
  page,
}, info) => {
  await api(page);
  await login(page);
  await navigate(page, "Inventory");
  await expect(
    page.getByText("GI1234567890ABCDEF", { exact: true }),
  ).toBeVisible();
  await page.getByRole("button", { name: "View", exact: true }).click();
  await expect(
    page.getByRole("heading", { name: "Piece details" }),
  ).toBeVisible();
  await page
    .getByRole("dialog")
    .getByRole("button", { name: "Close", exact: true })
    .click();
  await page.getByRole("button", { name: "العربية", exact: true }).click();
  await expect(page.locator("html")).toHaveAttribute("dir", "rtl");
  await expect(
    page.getByRole("heading", { name: "المخزون", exact: true }),
  ).toBeVisible();
  const layout = await page.evaluate(() => ({
    width: document.documentElement.scrollWidth,
    viewport: visualViewport?.width ?? innerWidth,
    inner: innerWidth,
    x: scrollX,
  }));
  expect(layout.width, JSON.stringify(layout)).toBeLessThanOrEqual(
    layout.viewport + 1,
  );
  await page.screenshot({
    path: `test-results/${info.project.name}-arabic-inventory.png`,
    fullPage: info.project.name === "desktop",
  });
});
test("cashier navigation does not expose admin or inventory write controls", async ({
  page,
}) => {
  await api(page, "cashier");
  await login(page);
  await expect(
    page.getByRole("heading", { name: "Monthly profit", exact: true }),
  ).toHaveCount(0);
  await expect(
    page.getByRole("button", {
      name: "Clear all development data",
      exact: true,
    }),
  ).toHaveCount(0);
  await navigate(page, "Inventory");
  await expect(
    page.getByRole("button", { name: "Bulk transfer", exact: true }),
  ).toHaveCount(0);
  const menu = page.getByRole("button", { name: "Menu", exact: true });
  if (await menu.isVisible()) await menu.click();
  await expect(
    page.locator("nav").getByRole("link", { name: "Staff accounts" }),
  ).toHaveCount(0);
  await page.goto("/staff");
  await expect(
    page.getByRole("heading", { name: "Overview", exact: true }),
  ).toBeVisible();
});

test("supplier balances, shortage warning and full settlement", async ({
  page,
}, info) => {
  await api(page);
  let settled = false;
  let cash = "20.00";
  let submitted: Record<string, unknown> | undefined;
  const balance = () => ({
    supplier_id: 1,
    making_usd: settled ? "0.00" : "30.00",
    gold_grams_by_purity: { "1": settled ? "0.000" : "2.000" },
    is_settled: settled,
  });
  await page.route("**/api/v1/suppliers/1/**", async (route) => {
    const path = new URL(route.request().url()).pathname;
    let body: unknown = [];
    if (path.endsWith("/balance")) body = balance();
    else if (path.endsWith("/availability"))
      body = { cash_usd: cash, gold_grams_by_purity: { "1": "2.000" } };
    else if (path.endsWith("/settlements")) {
      submitted = route.request().postDataJSON();
      settled = true;
      body = balance();
    }
    await route.fulfill({ json: body, headers: { "X-Total-Count": "0" } });
  });
  await login(page);
  await navigate(page, "Suppliers");
  await page.getByRole("button", { name: "View", exact: true }).click();
  await expect(
    page.getByRole("heading", { name: "We owe the supplier", exact: true }),
  ).toBeVisible();
  await expect(
    page.getByRole("heading", { name: "The supplier owes us", exact: true }),
  ).toBeVisible();
  await page
    .getByRole("button", { name: "Record settlement", exact: true })
    .click();
  const dialog = page.getByRole("dialog");
  await dialog.getByLabel("Location", { exact: true }).selectOption("1");
  await dialog.getByLabel("Purity", { exact: true }).selectOption("1");
  await dialog.getByLabel("Gold (g)", { exact: true }).fill("1");
  await dialog.getByLabel("Making charge (USD)", { exact: true }).fill("5");
  await expect(
    dialog.getByLabel("Settle account in full", { exact: true }),
  ).toBeDisabled();
  await expect(
    dialog.getByRole("button", { name: "Record settlement", exact: true }),
  ).toBeEnabled();
  await dialog.getByLabel("Gold (g)", { exact: true }).fill("2");
  await dialog.getByLabel("Making charge (USD)", { exact: true }).fill("30");
  await expect(dialog.getByRole("alert")).toHaveText(
    "Not enough cash or bulk gold at this location.",
  );
  await expect(
    dialog.getByRole("button", { name: "Record settlement", exact: true }),
  ).toBeDisabled();
  cash = "100.00";
  // Changing the bucket refreshes the availability rather than using an old quote.
  await dialog
    .getByLabel("Placement", { exact: true })
    .selectOption("showroom");
  await expect(
    dialog.getByLabel("Settle account in full", { exact: true }),
  ).toBeEnabled();
  await dialog.getByLabel("Settle account in full", { exact: true }).check();
  await page.screenshot({
    path: `test-results/${info.project.name}-supplier-settlement.png`,
  });
  await dialog
    .getByRole("button", { name: "Record settlement", exact: true })
    .click();
  await expect(page.getByRole("status")).toHaveText("Fully settled");
  expect(submitted).toMatchObject({
    direction: "sent",
    location_id: 1,
    purity_id: 1,
    placement: "showroom",
    making_usd: "30",
    gold_grams: "2",
    close_account: true,
  });
  await page.getByRole("button", { name: "العربية", exact: true }).click();
  await expect(
    page.getByRole("heading", { name: "مستحقات المورد علينا", exact: true }),
  ).toBeVisible();
});

test("monthly profit filters, breakdown and Arabic layout", async ({
  page,
}, info) => {
  await api(page);
  await login(page);
  await expect(
    page.getByRole("heading", { name: "Monthly profit", exact: true }),
  ).toBeVisible();
  await expect(page.getByText("$140.00", { exact: true })).toBeVisible();
  const request = page.waitForRequest((r) =>
    r.url().includes("/insights/monthly-profit?month=2026-04"),
  );
  await page.getByLabel("Month", { exact: true }).fill("2026-04");
  await request;
  const next = page.waitForRequest((r) =>
    r.url().includes("/insights/monthly-profit?month=2026-04&location_id=1"),
  );
  // The dashboard's cash selector and the report selector intentionally use separate locations.
  const panel = page.locator("section.panel").filter({
    has: page.getByRole("heading", { name: "Monthly profit", exact: true }),
  });
  await panel.getByLabel("Location", { exact: true }).selectOption("1");
  await next;
  await expect(
    panel.getByText("Supplier trades — separate from profit", { exact: true }),
  ).toBeVisible();
  await expect(panel.getByText("$285.00", { exact: true })).toBeVisible();
  await page.getByRole("button", { name: "العربية", exact: true }).click();
  await expect(
    page.getByRole("heading", { name: "الربح الشهري", exact: true }),
  ).toBeVisible();
  await page.screenshot({
    path: `test-results/${info.project.name}-monthly-profit-arabic.png`,
    fullPage: info.project.name === "desktop",
  });
  const layout = await page.evaluate(() => ({
    width: document.documentElement.scrollWidth,
    viewport: visualViewport?.width ?? innerWidth,
  }));
  expect(layout.width).toBeLessThanOrEqual(layout.viewport + 1);
});

test("development reset requires exact confirmation and refreshes dashboard", async ({
  page,
}) => {
  await api(page);
  let cleared = false,
    resetCalls = 0;
  await page.route("**/api/v1/development/**", async (route) => {
    const path = new URL(route.request().url()).pathname;
    if (path.endsWith("reset-status"))
      await route.fulfill({ json: { enabled: true } });
    else {
      expect(route.request().method()).toBe("POST");
      expect(route.request().postDataJSON()).toEqual({
        confirmation: "CLEAR DEVELOPMENT DATA",
      });
      cleared = true;
      resetCalls++;
      await route.fulfill({
        json: {
          cleared: true,
          photos_removed: 0,
          photo_cleanup_complete: true,
        },
      });
    }
  });
  await page.route("**/api/v1/inventory/items?**", async (route) => {
    if (cleared)
      await route.fulfill({ json: [], headers: { "X-Total-Count": "0" } });
    else await route.fallback();
  });
  await login(page);
  await page
    .getByRole("button", { name: "Clear all development data", exact: true })
    .click();
  const dialog = page.getByRole("dialog");
  await expect(
    dialog.getByRole("button", {
      name: "Delete development data",
      exact: true,
    }),
  ).toBeDisabled();
  await dialog
    .getByLabel("Confirmation phrase", { exact: true })
    .fill("clear development data");
  await expect(
    dialog.getByRole("button", {
      name: "Delete development data",
      exact: true,
    }),
  ).toBeDisabled();
  await dialog.getByRole("button", { name: "Cancel", exact: true }).click();
  expect(resetCalls).toBe(0);
  await page
    .getByRole("button", { name: "Clear all development data", exact: true })
    .click();
  await dialog
    .getByLabel("Confirmation phrase", { exact: true })
    .fill("CLEAR DEVELOPMENT DATA");
  await dialog
    .getByRole("button", { name: "Delete development data", exact: true })
    .click();
  await expect(page.getByRole("status")).toHaveText(
    "Development data cleared. Staff accounts are preserved.",
  );
  await expect(
    page
      .locator(".stat")
      .filter({ has: page.getByText("Available pieces", { exact: true }) })
      .locator("strong"),
  ).toHaveText("0");
  expect(resetCalls).toBe(1);
  await page.getByRole("button", { name: "العربية", exact: true }).click();
  await expect(
    page.getByRole("button", { name: "مسح جميع بيانات التطوير", exact: true }),
  ).toBeVisible();
});
