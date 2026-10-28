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
