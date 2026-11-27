import { expect, test } from "@playwright/test";
import { api, login, navigate } from "./helpers";

test("admin edits invoice details and voids the purchase from its row", async ({
  page,
}) => {
  await api(page);
  const purchase = {
    id: 21,
    invoice_number: "INV-1",
    location_id: 1,
    created_at: new Date().toISOString(),
    voided_at: null as string | null,
    void_reason: "",
  };
  await page.route("**/api/v1/purchases?**", (route) =>
    route.fulfill({
      json:
        route.request().headers()["x-business-unit"] === "factory"
          ? []
          : [purchase],
    }),
  );
  await page.route("**/api/v1/purchases/21", (route) => {
    expect(route.request().method()).toBe("PATCH");
    expect(route.request().postDataJSON()).toEqual({
      invoice_number: "INV-2",
      notes: null,
    });
    purchase.invoice_number = "INV-2";
    return route.fulfill({ json: purchase });
  });
  await page.route("**/api/v1/purchases/21/void", (route) => {
    expect(route.request().method()).toBe("POST");
    expect(route.request().postDataJSON()).toEqual({ reason: "Duplicate" });
    purchase.voided_at = new Date().toISOString();
    purchase.void_reason = "Duplicate";
    return route.fulfill({ json: purchase });
  });

  await login(page);
  await navigate(page, "Purchases");
  const row = page.getByRole("row").filter({ hasText: "INV-1" });
  await row.getByRole("button", { name: "Edit", exact: true }).click();
  const edit = page.getByRole("dialog", { name: "Edit purchase", exact: true });
  await edit.getByLabel("Invoice number", { exact: true }).fill("INV-2");
  await edit.getByRole("button", { name: "Save", exact: true }).click();
  await expect(edit).toBeHidden();

  const updated = page.getByRole("row").filter({ hasText: "INV-2" });
  await updated
    .getByRole("button", { name: "Void purchase", exact: true })
    .click();
  const cancel = page.getByRole("dialog", {
    name: "Void purchase",
    exact: true,
  });
  await cancel.getByLabel("Reason", { exact: true }).fill("Duplicate");
  await cancel
    .getByRole("button", { name: "Void purchase", exact: true })
    .click();
  await expect(cancel).toBeHidden();
  await expect(updated).toContainText("voided");
  await expect(updated.getByRole("button", { name: "Edit" })).toHaveCount(0);
  await expect(
    updated.getByRole("button", { name: "Void purchase" }),
  ).toHaveCount(0);
});
