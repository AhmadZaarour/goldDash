import { expect, test } from "@playwright/test";
import { api, navigate } from "./helpers";

function restoreSession() {
  sessionStorage.setItem("gold-refresh", "test-refresh");
}

test("admins correct records and confirm a permanent deletion", async ({
  page,
}) => {
  await api(page);
  await page.route("**/api/v1/admin/data", (route) =>
    route.fulfill({
      json: {
        tables: [
          {
            name: "categories",
            columns: [
              {
                name: "id",
                type: "integer",
                primary_key: true,
                editable: false,
              },
              { name: "name", type: "string", editable: true },
              {
                name: "description",
                type: "string",
                editable: true,
                nullable: true,
              },
            ],
          },
        ],
      },
    }),
  );
  const records = Array.from({ length: 26 }, (_, index) => ({
    key: { id: index + 1 },
    values: {
      id: index + 1,
      name: `Category ${index + 1}`,
      description: "Notes" as string | null,
    },
  }));
  let linked = true;
  await page.route("**/api/v1/admin/data/categories**", async (route) => {
    const request = route.request();
    if (request.method() === "PATCH") {
      expect(request.postDataJSON()).toEqual({
        key: { id: 26 },
        changes: { name: "Bracelets", description: null },
      });
      records[25].values.name = "Bracelets";
      records[25].values.description = null;
      return route.fulfill({ json: records[25] });
    }
    if (request.method() === "DELETE") {
      expect(request.postDataJSON()).toEqual({ key: { id: 26 } });
      if (linked) {
        linked = false;
        return route.fulfill({
          status: 409,
          json: { detail: "This record has linked records" },
        });
      }
      records.pop();
      return route.fulfill({ status: 204 });
    }
    const params = new URL(request.url()).searchParams;
    const offset = Number(params.get("offset"));
    const key = params.get("key");
    const results = key
      ? records.filter((record) => String(record.key.id) === key)
      : records;
    await route.fulfill({
      json: {
        items: results.slice(offset, offset + 25),
        total: results.length,
      },
    });
  });

  await page.addInitScript(restoreSession);
  await page.goto("/");
  await navigate(page, "Data management");
  await page.getByLabel("Find by primary key (id)").fill("26");
  await page.getByRole("button", { name: "Search", exact: true }).click();
  await expect(page.getByText("Category 26", { exact: true })).toBeVisible();
  await expect(
    page.getByText("Showing 1–1 of 1", { exact: true }),
  ).toBeVisible();
  await page.getByRole("button", { name: "Clear", exact: true }).click();
  await page.getByRole("button", { name: "Next", exact: true }).click();
  await page.getByRole("button", { name: "View / edit" }).click();
  const editor = page.getByRole("dialog", { name: "Record details" });
  await expect(editor.getByLabel("id", { exact: true })).toHaveAttribute(
    "readonly",
    "",
  );
  await editor.getByLabel("name", { exact: true }).fill("Bracelets");
  await editor.getByLabel("No value", { exact: true }).check();
  await editor.getByRole("button", { name: "Save" }).click();
  await expect(page.getByText("Bracelets", { exact: true })).toBeVisible();

  await page.getByRole("button", { name: "Delete", exact: true }).click();
  const confirmation = page.getByRole("dialog", { name: "Delete record" });
  await confirmation
    .getByRole("button", { name: "Cancel", exact: true })
    .click();
  await expect(page.getByText("Bracelets", { exact: true })).toBeVisible();
  await page.getByRole("button", { name: "Delete", exact: true }).click();
  await confirmation
    .getByRole("button", { name: "Delete", exact: true })
    .click();
  await expect(confirmation.getByRole("alert")).toContainText(
    "This record has linked records",
  );
  await confirmation
    .getByRole("button", { name: "Delete", exact: true })
    .click();
  await expect(page.getByText("Record deleted", { exact: true })).toBeVisible();
  await expect(
    page.getByText("Showing 1–25 of 25", { exact: true }),
  ).toBeVisible();
});

test("staff cannot open the admin data page", async ({ page }) => {
  await api(page, "cashier");
  await page.addInitScript(restoreSession);
  await page.goto("/admin-data");
  await expect(page).toHaveURL(/\/$/);
  await expect(page.getByRole("link", { name: "Data management" })).toHaveCount(
    0,
  );
});
