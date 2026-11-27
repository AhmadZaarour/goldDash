import { expect, test } from "@playwright/test";
import { api, login, navigate } from "./helpers";

test("the Overview location default prefills Showroom and Factory entries", async ({
  page,
}) => {
  await api(page);
  let locationId: number | null = null;
  await page.route("**/api/v1/locations/default", async (route) => {
    if (route.request().method() === "PUT") {
      locationId = route.request().postDataJSON().location_id;
    }
    await route.fulfill({ json: { location_id: locationId } });
  });
  await page.route("**/api/v1/locations?**", (route) =>
    route.fulfill({
      json: [
        { id: 1, name: "Main showroom", is_active: true },
        { id: 2, name: "Second showroom", is_active: true },
      ],
    }),
  );

  await login(page);
  const settings = page.locator("section").filter({
    has: page.getByRole("heading", { name: "Default location", exact: true }),
  });
  await settings.getByLabel("Location", { exact: true }).selectOption("2");
  await settings.getByRole("button", { name: "Save", exact: true }).click();
  await expect(settings.getByRole("status")).toHaveText("Saved successfully");
  expect(locationId).toBe(2);

  await navigate(page, "Sales");
  const openSale = page.getByRole("button", {
    name: "Customer sale",
    exact: true,
  });
  await openSale.click();
  const dialog = page.getByRole("dialog");
  const saleLocation = dialog.getByLabel("Location", { exact: true });
  await expect(saleLocation).toHaveValue("2");
  await saleLocation.selectOption("1");
  await expect(saleLocation).toHaveValue("1");
  await page.keyboard.press("Escape");
  await expect(dialog).toBeHidden();
  await page.getByLabel("Workspace", { exact: true }).selectOption("factory");
  await expect(settings.getByLabel("Location", { exact: true })).toHaveValue(
    "2",
  );
  await navigate(page, "Inventory");
  await page
    .getByRole("button", { name: "Raw gold transfer", exact: true })
    .click();
  await expect(
    dialog.getByLabel("Source location", { exact: true }),
  ).toHaveValue("2");
  await expect(
    dialog.getByLabel("Destination location", { exact: true }),
  ).toHaveValue("");
});
