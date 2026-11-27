import { expect, test, type Page } from "@playwright/test";
import Decimal from "decimal.js";
import { api, login, navigate } from "./helpers";

test("admin pauses the live quote, keeps the manual ounce after reload, and resumes", async ({
  page,
}) => {
  await api(page);
  let manualOunce: string | null = null;
  await page.route("**/api/v1/gold-price/settings", (route) =>
    route.fulfill({ json: { manual_ounce_usd: manualOunce } }),
  );
  await page.route("**/api/v1/gold-price/quote-mode", async (route) => {
    expect(route.request().method()).toBe("PUT");
    manualOunce = route.request().postDataJSON().manual_ounce_usd;
    await route.fulfill({ json: { manual_ounce_usd: manualOunce } });
  });
  await page.route("**/api/v1/gold-price", (route) =>
    manualOunce === null
      ? route.fallback()
      : route.fulfill({
          json: {
            ounce_usd: manualOunce,
            gram_24k_usd: "110",
            gram_21k_usd: "96.73",
            gram_18k_usd: "82.91",
            fetched_at: new Date(Date.now() - 600_000).toISOString(),
            stale: false,
            quote_mode: "manual",
          },
        }),
  );
  await login(page);

  const settings = page.getByRole("button", { name: "Gold quote settings" });
  const dialog = page.getByRole("dialog", { name: "Gold quote settings" });
  const source = dialog.getByRole("combobox", { name: "Quote source" });
  await settings.click();
  await source.selectOption("manual");
  await dialog.getByLabel("Manual 24K ounce (USD)").fill("3421");
  await dialog.getByRole("button", { name: "Save" }).click();
  await expect(page.getByText("Manual gold quote")).toBeVisible();
  await expect(page.getByText("$3421.00", { exact: true })).toBeVisible();

  await page.reload();
  await expect(page.getByText("Manual gold quote")).toBeVisible();
  await settings.click();
  await expect(source).toHaveValue("manual");
  await expect(dialog.getByLabel("Manual 24K ounce (USD)")).toHaveValue("3421");
  await source.selectOption("live");
  await dialog.getByRole("button", { name: "Save" }).click();
  await expect(page.getByText("Latest quote")).toBeVisible();
  await expect(page.getByText("$3110.00", { exact: true })).toBeVisible();
});

async function customerPrices(page: Page, initialBuy = "0", initialSell = "0") {
  const settings: Record<
    string,
    { buy_adjustment_usd: string; sell_adjustment_usd: string }
  > = {
    showroom: {
      buy_adjustment_usd: initialBuy,
      sell_adjustment_usd: initialSell,
    },
    factory: { buy_adjustment_usd: "0", sell_adjustment_usd: "0" },
  };
  const writes: Record<string, unknown>[] = [];
  await page.route("**/api/v1/gold-price/settings", async (route) => {
    const unit = route.request().headers()["x-business-unit"] || "showroom";
    if (route.request().method() === "PUT") {
      const body = route.request().postDataJSON();
      writes.push({ unit, ...body });
      settings[unit] = body;
    }
    await route.fulfill({ json: { unit, ...settings[unit] } });
  });
  await page.route("**/api/v1/gold-price", async (route) => {
    const unit = route.request().headers()["x-business-unit"] || "showroom";
    const raw = {
      ounce_usd: "3110",
      gram_24k_usd: "100",
      gram_21k_usd: "87.939698",
      gram_18k_usd: "75.376884",
      fetched_at: new Date().toISOString(),
      stale: false,
    };
    function profile(adjustment: string) {
      const ounce = new Decimal(raw.ounce_usd).plus(adjustment),
        gram = ounce.div("31.1");
      return {
        ...raw,
        ounce_adjustment_usd: adjustment,
        ounce_usd: ounce.toString(),
        gram_24k_usd: gram.toString(),
        gram_21k_usd: gram.mul("0.875").div("0.995").toString(),
        gram_18k_usd: gram.mul("0.75").div("0.995").toString(),
        available: true,
      };
    }
    await route.fulfill({
      json: {
        ...raw,
        customer_buy: profile(settings[unit].buy_adjustment_usd),
        customer_sell: profile(settings[unit].sell_adjustment_usd),
      },
    });
  });
  return writes;
}

test("admin adjusts ounces from zero and each workspace keeps its own defaults", async ({
  page,
}) => {
  await api(page);
  const writes = await customerPrices(page);
  await login(page);
  await page
    .getByRole("button", { name: "Customer price adjustments", exact: true })
    .click();
  const dialog = page.getByRole("dialog", {
    name: "Customer price adjustments",
    exact: true,
  });
  await expect(
    dialog.getByLabel("Buying ounce adjustment (USD)", { exact: true }),
  ).toHaveValue("0");
  await expect(
    dialog.getByLabel("Selling ounce adjustment (USD)", { exact: true }),
  ).toHaveValue("0");
  await dialog
    .getByLabel("Buying ounce adjustment (USD)", { exact: true })
    .fill("-40");
  await dialog
    .getByLabel("Selling ounce adjustment (USD)", { exact: true })
    .fill("40");
  await dialog.getByRole("button", { name: "Save", exact: true }).click();
  await expect(dialog).toHaveCount(0);
  const prices = page.getByRole("table", {
    name: "Customer gold prices",
    exact: true,
  });
  await expect(
    prices.getByRole("row").filter({ hasText: "Customer buying" }),
  ).toContainText("3070.00");
  await expect(
    prices.getByRole("row").filter({ hasText: "Customer selling" }),
  ).toContainText("3150.00");
  expect(writes).toEqual([
    { unit: "showroom", buy_adjustment_usd: "-40", sell_adjustment_usd: "40" },
  ]);
  await page.getByLabel("Workspace", { exact: true }).selectOption("factory");
  await page
    .getByRole("button", { name: "Customer price adjustments", exact: true })
    .click();
  await expect(
    dialog.getByLabel("Buying ounce adjustment (USD)", { exact: true }),
  ).toHaveValue("0");
  await expect(
    dialog.getByLabel("Selling ounce adjustment (USD)", { exact: true }),
  ).toHaveValue("0");
});

test("cashier customer rates use buy and sell profiles while actual totals stay editable", async ({
  page,
}) => {
  await api(page, "cashier");
  await customerPrices(page, "-40", "40");
  await page.route("**/api/v1/products?**", (route) =>
    route.fulfill({
      json: [
        { id: 1, name: "Ring", inventory_type: "item", purity_id: 1 },
        { id: 2, name: "Bulk", inventory_type: "bulk", purity_id: 1 },
      ],
      headers: { "X-Total-Count": "2" },
    }),
  );
  let sale: Record<string, unknown> | undefined,
    purchase: Record<string, unknown> | undefined;
  await page.route("**/api/v1/sales/item", async (route) => {
    sale = route.request().postDataJSON();
    await route.fulfill({ status: 201, json: { id: 11, location_id: 1 } });
  });
  await page.route("**/api/v1/purchases/customer-stock", async (route) => {
    purchase = route.request().postDataJSON();
    await route.fulfill({ status: 201, json: { id: 12, location_id: 1 } });
  });
  await login(page);
  await expect(
    page.getByRole("button", {
      name: "Customer price adjustments",
      exact: true,
    }),
  ).toHaveCount(0);
  await navigate(page, "Sales");
  await page
    .getByRole("button", { name: "Customer sale", exact: true })
    .click();
  let dialog = page.getByRole("dialog", { name: "Customer sale", exact: true });
  await dialog.getByLabel("Location", { exact: true }).selectOption("1");
  await dialog.getByLabel("Product", { exact: true }).selectOption("1");
  await expect(
    dialog.getByLabel("Calculated gold price / gram", { exact: true }),
  ).toHaveText("101.2862");
  await dialog.getByLabel("Discount (USD)", { exact: true }).fill("0");
  await dialog.getByLabel("Final price (USD)", { exact: true }).fill("321.45");
  await dialog.getByRole("button", { name: "Confirm", exact: true }).click();
  await expect(dialog).toHaveCount(0);
  expect(sale).toMatchObject({
    items: [{ inventory_item_id: 1, sell_price: "321.45" }],
  });
  await navigate(page, "Purchases");
  await page
    .getByRole("button", { name: "Customer bulk purchase", exact: true })
    .click();
  dialog = page.getByRole("dialog", {
    name: "Customer bulk purchase",
    exact: true,
  });
  await dialog.getByLabel("Location", { exact: true }).selectOption("1");
  await dialog.getByLabel("Product", { exact: true }).selectOption("2");
  await expect(
    dialog.getByLabel("Calculated gold price / gram", { exact: true }),
  ).toHaveText("98.7138");
  await dialog.getByLabel("Weight (g)", { exact: true }).fill("5");
  await dialog.getByLabel("Total paid (USD)", { exact: true }).fill("280.55");
  await dialog.getByRole("button", { name: "Confirm", exact: true }).click();
  await expect(dialog).toHaveCount(0);
  expect(purchase).toMatchObject({ weight: "5", paid_usd: "280.55" });
});

test("trade history displays the saved ounce basis alongside recorded gram rates", async ({
  page,
}) => {
  await api(page, "cashier");
  await customerPrices(page, "-99", "99");
  await page.route("**/api/v1/sales?**", (route) =>
    route.fulfill({
      json: [
        {
          id: 11,
          location_id: 1,
          invoice_number: "SALE-11",
          kind: "customer",
          created_at: new Date().toISOString(),
          market_ounce_usd: "3110",
          ounce_adjustment_usd: "40",
          applied_ounce_usd: "3150",
        },
      ],
      headers: { "X-Total-Count": "1" },
    }),
  );
  await page.route("**/api/v1/sales/item/11", (route) =>
    route.fulfill({
      json: [
        {
          id: 1,
          inventory_item_id: 1,
          gold_price_per_gram: "101.2862",
          sell_price: "321.45",
        },
      ],
    }),
  );
  await login(page);
  await navigate(page, "Sales");
  await page.getByRole("button", { name: "View", exact: true }).click();
  const detail = page.getByRole("dialog", { name: "Details", exact: true });
  await expect(detail.getByText("$3150.00", { exact: true })).toBeVisible();
  await expect(detail.getByText("$40.00", { exact: true })).toBeVisible();
  await expect(
    detail.getByText("Applied ounce (USD)", { exact: true }),
  ).toBeVisible();
});
