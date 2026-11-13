import { expect, type Page } from "@playwright/test";
export async function api(page: Page, role = "admin") {
  const user = { id: 1, username: "Ahmad", email: "owner@example.com", role };
  await page.route("**/api/v1/**", async (route) => {
    const req = route.request();
    const url = new URL(req.url());
    const path = url.pathname.replace("/api/v1", "");
    let body: unknown = [];
    if (path === "/auth/login" || path === "/auth/refresh")
      body = { access_token: "test-token", refresh_token: "test-refresh" };
    else if (path === "/auth/me") body = user;
    else if (path === "/operations/overview")
      body = { cash_usd: "125", available_pieces: 1, bulk: [] };
    else if (path === "/operations/staff") body = [user];
    else if (path === "/operations/profit")
      body = {
        revenue_usd: "500",
        cost_of_sales_usd: "260",
        expenses_usd: "0",
        profit_usd: "240",
        uncosted_trades: 0,
      };
    else if (path === "/gold-price")
      body = {
        ounce_usd: "3110",
        gram_24k_usd: "100",
        gram_21k_usd: "87.939698",
        gram_18k_usd: "75.376884",
        fetched_at: new Date().toISOString(),
        stale: false,
      };
    else if (path === "/development/reset-status") body = { enabled: false };
    else if (path === "/insights/monthly-profit")
      body = {
        month: url.searchParams.get("month"),
        timezone: "Asia/Beirut",
        service_sales_usd: "0",
        service_sales_count: 0,
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
          base_cost_usd: "165.00",
          status: "in_stock",
          location_id: 1,
          purchase_item_id: 1,
          image_url: null,
        },
      ];
    else if (path === "/inventory/items/1")
      body = {
        id: 1,
        barcode: "GI1234567890ABCDEF",
        product_name: "Classic gold ring",
        purity_id: 1,
        weight: "2.500",
        base_cost_usd: "165.00",
        status: "in_stock",
        location_id: 1,
      };
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
      body = [
        {
          id: 1,
          name: "22K",
          karat: 24,
          purity: "99.5",
          repayment_factor: "1",
        },
      ];
    else if (path === "/categories") body = [{ id: 1, name: "Rings" }];
    else if (path === "/cash/summary")
      body = {
        net_usd: "125.00",
        received_usd: "200.00",
        service_received_usd: "0",
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
export async function login(page: Page) {
  await page.goto("/");
  await page.getByLabel("Email", { exact: true }).fill("owner@example.com");
  await page.getByLabel("Password", { exact: true }).fill("TestPassword123!");
  await page.getByRole("button", { name: "Sign in", exact: true }).click();
  await expect(
    page.getByRole("heading", { name: "Overview", exact: true }),
  ).toBeVisible();
}
export async function navigate(page: Page, label: string) {
  const menu = page.getByRole("button", { name: "Menu", exact: true });
  if (await menu.isVisible()) await menu.click();
  await page
    .locator("nav")
    .getByRole("link", { name: label, exact: true })
    .click();
}
