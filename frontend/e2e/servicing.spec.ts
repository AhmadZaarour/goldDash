import { expect, test } from "@playwright/test";
import { api, login, navigate } from "./helpers";

const job = {
  id: 1,
  barcode: "SV001",
  status: "in_progress",
  notes: null as string | null,
  cost: "0",
  sale: null as Record<string, unknown> | null,
};

test("intake generates barcode and allows optional notes and two statuses", async ({
  page,
}) => {
  await api(page, "employee");
  let saved: typeof job | undefined;
  await page.route("**/api/v1/servicing**", async (route) => {
    const request = route.request();
    if (request.method() === "POST") {
      expect(request.postDataJSON()).toEqual({
        status: "in_progress",
        notes: null,
      });
      expect(request.headers()["idempotency-key"]).toBeTruthy();
      saved = { ...job };
      return route.fulfill({ status: 201, json: saved });
    }
    if (request.method() === "PATCH") {
      saved = { ...saved!, ...request.postDataJSON() };
      return route.fulfill({ json: saved });
    }
    return route.fulfill({ json: saved ? [saved] : [] });
  });
  await login(page);
  await navigate(page, "Servicing");
  await expect(
    page.getByRole("button", { name: "Service sale", exact: true }),
  ).toHaveCount(0);
  await page.getByRole("button", { name: "New service", exact: true }).click();
  const intake = page.getByRole("dialog", { name: "New service", exact: true });
  for (const label of ["Customer", "Cost (USD)", "Barcode"])
    await expect(intake.getByLabel(label, { exact: true })).toHaveCount(0);
  await expect(intake.getByLabel("Status", { exact: true })).toHaveValue(
    "in_progress",
  );
  await expect(
    intake.getByLabel("Status", { exact: true }).locator("option"),
  ).toHaveCount(3);
  await intake.getByRole("button", { name: "Save", exact: true }).click();
  const details = page.getByRole("dialog", {
    name: "Service details",
    exact: true,
  });
  await expect(details.getByText("SV001", { exact: true })).toBeVisible();
  await details.getByLabel("Status", { exact: true }).selectOption("finished");
  await details
    .getByLabel("Notes", { exact: true })
    .fill("Ready for collection");
  await details.getByRole("button", { name: "Save", exact: true }).click();
  await expect.poll(() => saved?.status).toBe("finished");
  await details.getByRole("button", { name: "Close", exact: true }).click();
  await expect(
    page.getByRole("row").filter({ hasText: "SV001" }),
  ).toContainText("Ready for collection");
});

test("cashier checkout blocks unfinished and paid jobs and clears stale lookups", async ({
  page,
}) => {
  await api(page, "cashier");
  let service = { ...job };
  await page.route("**/api/v1/servicing**", async (route) =>
    route.fulfill({ json: [service] }),
  );
  await login(page);
  await navigate(page, "Servicing");
  await expect(
    page.getByRole("button", { name: "New service", exact: true }),
  ).toHaveCount(0);
  await page.getByRole("button", { name: "Service sale", exact: true }).click();
  const checkout = page.getByRole("dialog", {
    name: "Service sale",
    exact: true,
  });
  const input = checkout.getByLabel("Service barcode", { exact: true });
  const find = checkout.getByRole("button", {
    name: "Find service",
    exact: true,
  });
  const submit = checkout.getByRole("button", {
    name: "Submit payment",
    exact: true,
  });
  await input.fill("SV001");
  await find.click();
  await expect(checkout.getByRole("status")).toHaveText(
    "Finish the service before collecting payment",
  );
  await expect(submit).toBeDisabled();
  service = { ...service, status: "finished" };
  await find.click();
  await expect(submit).toBeEnabled();
  await input.fill("UNKNOWN");
  await expect(submit).toBeDisabled();
  service = { ...service, sale: { id: 1, amount_usd: "25" } };
  await input.fill("SV001");
  await find.click();
  await expect(checkout.getByRole("status")).toHaveText(
    "This service has already been paid",
  );
  await expect(submit).toBeDisabled();
});
