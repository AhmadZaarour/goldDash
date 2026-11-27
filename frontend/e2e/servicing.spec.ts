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
  await login(page, "Production");
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

test("admins correct expense records and service payments from their source screens", async ({
  page,
}) => {
  await api(page);
  let expense = {
    id: 2,
    kind: "expense",
    description: "Packaging",
    amount_usd: "-25",
  };
  let expenseDeleted = false;
  let service = {
    ...job,
    status: "finished",
    sale: { id: 1, amount_usd: "40" } as Record<string, unknown> | null,
  };
  await page.route("**/api/v1/cash/entries?**", (route) =>
    route.fulfill({
      json: [
        {
          id: 1,
          kind: "service_sale",
          description: "Service SV001",
          amount_usd: "40",
        },
        ...(expenseDeleted ? [] : [expense]),
      ],
    }),
  );
  await page.route("**/api/v1/cash/outflows/2", (route) => {
    if (route.request().method() === "DELETE") {
      expenseDeleted = true;
      return route.fulfill({ status: 204 });
    }
    const data = route.request().postDataJSON();
    expense = {
      ...expense,
      description: data.description,
      amount_usd: "-" + data.amount_usd,
    };
    return route.fulfill({ json: expense });
  });
  await page.route("**/api/v1/servicing", (route) =>
    route.fulfill({ json: [service] }),
  );
  await page.route("**/api/v1/servicing/sales/1", (route) => {
    if (route.request().method() === "DELETE") {
      service = { ...service, sale: null };
      return route.fulfill({ status: 204 });
    }
    const sale = { id: 1, amount_usd: route.request().postDataJSON().cost };
    service = { ...service, sale };
    return route.fulfill({ json: sale });
  });

  await login(page);
  await navigate(page, "Cash drawer");
  await expect(
    page.getByRole("heading", { name: "Cash drawer" }),
  ).toBeVisible();
  await page
    .locator(".filters")
    .getByLabel("Location", { exact: true })
    .selectOption("1");
  const linked = page.getByRole("row").filter({ hasText: "Service SV001" });
  await expect(linked).toBeVisible();
  await expect(linked.getByRole("button")).toHaveCount(0);

  const expenseRow = page.getByRole("row").filter({ hasText: "Packaging" });
  await expenseRow.getByRole("button", { name: "Edit", exact: true }).click();
  const cashEdit = page.getByRole("dialog", { name: "Edit cash outflow" });
  await cashEdit
    .getByLabel("Description", { exact: true })
    .fill("Packaging supplies");
  await cashEdit.getByRole("button", { name: "Save", exact: true }).click();
  await expect(expenseRow).toContainText("Packaging supplies");
  await expenseRow.getByRole("button", { name: "Delete", exact: true }).click();
  await page
    .getByRole("dialog", { name: "Delete record" })
    .getByRole("button", { name: "Delete", exact: true })
    .click();
  await expect(expenseRow).toHaveCount(0);

  await navigate(page, "Servicing");
  const serviceRow = page.getByRole("row").filter({ hasText: "SV001" });
  await serviceRow.getByRole("button", { name: "View", exact: true }).click();
  const details = page.getByRole("dialog", { name: "Service details" });
  await details.getByRole("button", { name: "Edit payment" }).click();
  await details.getByLabel("Amount (USD)", { exact: true }).fill("45");
  await details.getByRole("button", { name: "Save", exact: true }).click();
  await expect(details).toContainText("$45.00");
  await details.getByRole("button", { name: "Void service payment" }).click();
  await page
    .getByRole("dialog", { name: "Void service payment" })
    .getByRole("button", { name: "Void service payment" })
    .click();
  await expect(details).toContainText("Unpaid");
  await details.getByRole("button", { name: "Close", exact: true }).click();
  await expect(
    serviceRow.getByRole("button", { name: "Delete", exact: true }),
  ).toBeVisible();
});
