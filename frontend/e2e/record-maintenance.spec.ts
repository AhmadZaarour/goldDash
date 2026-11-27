import { expect, test, type Page } from "@playwright/test";
import { api, navigate } from "./helpers";

async function openPage(page: Page, name: string) {
  await page.addInitScript(() =>
    sessionStorage.setItem("gold-refresh", "test-refresh"),
  );
  await page.goto("/");
  await expect(
    page.getByRole("heading", { name: "Overview", exact: true }),
  ).toBeVisible();
  await navigate(page, name);
}

test("catalog deletion requires confirmation and reports linked history", async ({
  page,
}) => {
  await api(page);
  let attempts = 0;
  await page.route("**/api/v1/products/1", async (route) => {
    expect(route.request().method()).toBe("DELETE");
    attempts++;
    if (attempts === 1) {
      return route.fulfill({
        status: 409,
        json: { detail: "Product is referenced by existing records" },
      });
    }
    return route.fulfill({ status: 204 });
  });
  await page.route("**/api/v1/products?**", (route) =>
    attempts === 2 ? route.fulfill({ json: [] }) : route.fallback(),
  );

  await openPage(page, "Catalog");
  await page.getByRole("button", { name: "Delete", exact: true }).click();
  const dialog = page.getByRole("dialog", { name: "Delete record" });
  await expect(
    dialog.getByText("Classic gold ring", { exact: true }),
  ).toBeVisible();
  await dialog.getByRole("button", { name: "Cancel", exact: true }).click();
  expect(attempts).toBe(0);

  await page.getByRole("button", { name: "Delete", exact: true }).click();
  await dialog.getByRole("button", { name: "Delete", exact: true }).click();
  await expect(dialog.getByRole("alert")).toContainText(
    "Product is referenced by existing records",
  );
  await dialog.getByRole("button", { name: "Delete", exact: true }).click();
  await expect(
    page.getByText("No matching records", { exact: true }),
  ).toBeVisible();
  await expect(dialog).toHaveCount(0);
});

test("staff editing hides self-deactivation and supports deactivating another account", async ({
  page,
}) => {
  await api(page);
  const owner = {
    id: 1,
    username: "Ahmad",
    email: "owner@example.com",
    role: "admin",
    workspace_access: "both",
    is_active: true,
  };
  const cashier = {
    id: 2,
    username: "Lina",
    email: "lina@example.com",
    role: "cashier",
    workspace_access: "showroom",
    is_active: true,
  };
  await page.route("**/api/v1/operations/staff?**", (route) =>
    route.fulfill({ json: [owner, cashier] }),
  );
  await page.route("**/api/v1/operations/staff/2", async (route) => {
    expect(route.request().method()).toBe("PATCH");
    expect(route.request().postDataJSON()).toEqual({
      username: "Lina K",
      role: "employee",
      is_active: false,
    });
    Object.assign(cashier, route.request().postDataJSON(), {
      workspace_access: "factory",
    });
    await route.fulfill({ json: cashier });
  });

  await openPage(page, "Staff accounts");
  const ownerRow = page.locator("tr").filter({ hasText: "owner@example.com" });
  await expect(
    ownerRow.getByRole("button", { name: "Delete", exact: true }),
  ).toHaveCount(0);
  await ownerRow.getByRole("button", { name: "Edit", exact: true }).click();
  const dialog = page.getByRole("dialog", { name: "Edit staff account" });
  await expect(dialog.getByLabel("Active", { exact: true })).toHaveCount(0);
  await dialog.getByRole("button", { name: "Close", exact: true }).click();

  const staffRow = page.locator("tr").filter({ hasText: "lina@example.com" });
  await staffRow.getByRole("button", { name: "Edit", exact: true }).click();
  await dialog.getByLabel("Username", { exact: true }).fill("Lina K");
  await dialog.getByLabel("Role", { exact: true }).selectOption("employee");
  await expect(
    dialog.getByLabel("Workspace access", { exact: true }),
  ).toHaveCount(0);
  await dialog.getByLabel("Active", { exact: true }).uncheck();
  await dialog.getByRole("button", { name: "Save", exact: true }).click();
  await expect(staffRow.getByText("Lina K", { exact: true })).toBeVisible();
  await expect(staffRow.getByText("factory", { exact: true })).toBeVisible();
  await expect(staffRow.getByText("Inactive", { exact: true })).toBeVisible();
});

test("staff creation assigns workspace access through the selected role", async ({
  page,
}) => {
  await api(page);
  await openPage(page, "Staff accounts");
  const registration = page.waitForRequest((request) =>
    request.url().endsWith("/api/v1/auth/register"),
  );
  await expect(
    page.getByLabel("Workspace access", { exact: true }),
  ).toHaveCount(0);
  await page.getByLabel("Email", { exact: true }).fill("noor@example.com");
  await page.getByLabel("Username", { exact: true }).fill("Noor");
  await page.getByLabel("Password", { exact: true }).fill("TestPassword123!");
  await page.getByLabel("Role", { exact: true }).selectOption("employee");
  await page.getByRole("button", { name: "Create", exact: true }).click();
  expect((await registration).postDataJSON()).toEqual({
    email: "noor@example.com",
    username: "Noor",
    password: "TestPassword123!",
    role: "employee",
  });
});

test("admins can correct a supplier settlement note", async ({ page }) => {
  await api(page);
  const entry = {
    id: 8,
    kind: "settlement",
    note: "Old note",
    making_usd: "25.00",
  };
  await page.route("**/api/v1/suppliers/1/balance", (route) =>
    route.fulfill({
      json: { is_settled: true, making_usd: "0", gold_24k: "0" },
    }),
  );
  await page.route("**/api/v1/suppliers/1/ledger?**", (route) =>
    route.fulfill({ json: [entry] }),
  );
  await page.route("**/api/v1/suppliers/1/ledger/8", async (route) => {
    expect(route.request().method()).toBe("PATCH");
    expect(route.request().postDataJSON()).toEqual({
      note: "Receipt corrected",
    });
    entry.note = "Receipt corrected";
    await route.fulfill({ json: entry });
  });

  await openPage(page, "Suppliers");
  await page.getByRole("button", { name: "View", exact: true }).click();
  await page.getByRole("button", { name: "Edit note", exact: true }).click();
  const dialog = page.getByRole("dialog", { name: "Edit note" });
  await expect(dialog.getByLabel("Notes", { exact: true })).toHaveValue(
    "Old note",
  );
  await dialog.getByLabel("Notes", { exact: true }).fill("Receipt corrected");
  await dialog.getByRole("button", { name: "Save", exact: true }).click();
  await expect(
    page.getByText("Receipt corrected", { exact: true }),
  ).toBeVisible();
  await expect(
    page.getByRole("button", { name: "Reverse", exact: true }),
  ).toBeVisible();
});
