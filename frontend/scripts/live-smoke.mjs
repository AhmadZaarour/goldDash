import { chromium } from "playwright";
import assert from "node:assert/strict";
const browser = await chromium.launch({
  executablePath: process.env.CHROMIUM_PATH || undefined,
});
const page = await browser.newPage({ viewport: { width: 1280, height: 900 } });
page.on("pageerror", (error) => {
  throw error;
});
const base = process.env.UI_TEST_BASE || "http://127.0.0.1:5175";
async function nav(label) {
  await page
    .locator("nav")
    .getByRole("link", { name: label, exact: true })
    .click();
}
async function save() {
  await page
    .getByRole("dialog")
    .getByRole("button", { name: "Save", exact: true })
    .click();
  await page.getByRole("dialog").waitFor({ state: "detached" });
}
try {
  await page.goto(base);
  await page
    .getByLabel("Email", { exact: true })
    .fill(process.env.UI_TEST_EMAIL);
  await page
    .getByLabel("Password", { exact: true })
    .fill(process.env.UI_TEST_PASSWORD);
  await page.getByRole("button", { name: "Sign in", exact: true }).click();
  await page.getByRole("heading", { name: "Overview", exact: true }).waitFor();
  await nav("Catalog");
  await page.getByRole("button", { name: "Categories", exact: true }).click();
  await page.getByRole("button", { name: "Create", exact: true }).click();
  await page.getByLabel("Name", { exact: true }).fill("Rings");
  await save();
  await page
    .getByRole("button", { name: "Gold purities", exact: true })
    .click();
  await page.getByRole("button", { name: "Create", exact: true }).click();
  await page.getByLabel("Name", { exact: true }).fill("22K");
  await page.getByLabel("Karat", { exact: true }).fill("22");
  await page.getByLabel("Purity (%)", { exact: true }).fill("91.6");
  await save();
  await page.getByRole("button", { name: "Locations", exact: true }).click();
  await page.getByRole("button", { name: "Create", exact: true }).click();
  await page.getByLabel("Name", { exact: true }).fill("Main showroom");
  await page.getByLabel("Code", { exact: true }).fill("MAIN");
  await save();
  await nav("Suppliers");
  await page.getByRole("button", { name: "Create", exact: true }).click();
  await page.getByLabel("Name", { exact: true }).fill("Workshop");
  await page.getByLabel("Phone", { exact: true }).fill("123456");
  await save();
  await nav("Catalog");
  await page.getByRole("button", { name: "Products", exact: true }).click();
  await page.getByRole("button", { name: "Create", exact: true }).click();
  await page.getByLabel("SKU", { exact: true }).fill("RING-01");
  await page.getByLabel("Name", { exact: true }).fill("Classic ring");
  await page
    .getByLabel("Category", { exact: true })
    .selectOption({ label: "Rings" });
  await page
    .getByLabel("Purity", { exact: true })
    .selectOption({ label: "22K" });
  await page.getByLabel("Type", { exact: true }).selectOption("item");
  await save();
  await nav("Purchases");
  await page
    .getByRole("button", { name: "Item purchase", exact: true })
    .click();
  await page
    .getByRole("dialog")
    .getByLabel("Location", { exact: true })
    .selectOption({ label: "Main showroom" });
  await page
    .getByLabel("Supplier", { exact: true })
    .selectOption({ label: "Workshop" });
  await page
    .getByLabel("Product", { exact: true })
    .selectOption({ label: "Classic ring · RING-01" });
  for (const [label, value] of [
    ["Weight (g)", "2.5"],
    ["Gold price / gram", "70"],
    ["Gold charge (g)", "2.5"],
    ["Making charge (USD)", "8.60"],
  ])
    await page.getByLabel(label, { exact: true }).fill(value);
  const purchaseResponse = page.waitForResponse(
    (r) =>
      r.url().endsWith("/api/v1/purchases/item") &&
      r.request().method() === "POST",
  );
  await page.getByRole("button", { name: "Confirm", exact: true }).click();
  assert.equal((await purchaseResponse).status(), 201);
  await page.getByRole("dialog").waitFor({ state: "detached" });
  await nav("Inventory");
  await page.getByRole("button", { name: "View", exact: true }).click();
  await page
    .getByLabel("Take / choose photo")
    .setInputFiles(process.env.UI_TEST_PHOTO);
  await page.getByRole("dialog").waitFor({ state: "detached" });
  await nav("Sales");
  await page
    .getByRole("button", { name: "Customer sale", exact: true })
    .click();
  await page
    .getByRole("dialog")
    .getByLabel("Location", { exact: true })
    .selectOption({ label: "Main showroom" });
  await page
    .getByLabel("Product", { exact: true })
    .selectOption({ label: "Classic ring · RING-01" });
  await page.getByLabel("Gold price / gram", { exact: true }).fill("100");
  await page.getByLabel("Discount (USD)", { exact: true }).fill("5");
  await page.getByLabel("Final price (USD)", { exact: true }).fill("125.25");
  const saleResponse = page.waitForResponse(
    (r) =>
      r.url().endsWith("/api/v1/sales/item") && r.request().method() === "POST",
  );
  await page.getByRole("button", { name: "Confirm", exact: true }).click();
  assert.equal((await saleResponse).status(), 201);
  await page.getByRole("dialog").waitFor({ state: "detached" });
  await nav("Cash drawer");
  await page
    .locator(".filters")
    .getByLabel("Location", { exact: true })
    .selectOption({ label: "Main showroom" });
  await page.getByText("$125.25", { exact: true }).first().waitFor();
  await page.getByRole("button", { name: "Expense", exact: true }).click();
  await page
    .getByRole("dialog")
    .getByLabel("Location", { exact: true })
    .selectOption({ label: "Main showroom" });
  await page.getByLabel("Amount (USD)", { exact: true }).fill("12.50");
  await page.getByLabel("Description", { exact: true }).fill("Packaging");
  await save();
  await page.getByText("$112.75", { exact: true }).waitFor();
  await page.getByRole("button", { name: "العربية", exact: true }).click();
  assert.equal(await page.locator("html").getAttribute("dir"), "rtl");
  await page.screenshot({
    path: process.env.UI_TEST_SCREENSHOT || "/tmp/golddash-live.png",
    fullPage: true,
  });
  console.log(
    "Live API workflow passed: login, catalog, purchase, photo, cash sale, expense, Arabic RTL.",
  );
} finally {
  try {
    await page.evaluate(async () => {
      const token = sessionStorage.getItem("gold-refresh");
      if (token)
        await fetch("/api/v1/auth/logout", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ refresh_token: token }),
        });
    });
  } catch {}
  await browser.close();
}
