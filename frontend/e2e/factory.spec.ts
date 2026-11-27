import { test, expect } from "@playwright/test";
import { api, login, navigate } from "./helpers";

test("admins correct production steps and reverse internal transactions from their tables", async ({
  page,
}) => {
  await api(page);
  const stepTime = "2026-01-01T10:00:00Z";
  const batch = {
    id: 1,
    tracking_mode: "weight",
    status: "in_progress",
    reference: "Batch A",
    details: {
      inputs: [],
      steps: [
        { name: "Polishing", created_at: stepTime, outputs: [], scrap: [] },
      ],
    },
  };
  const invoice = { id: 2, note: "Original note", is_reversed: false };
  await page.route("**/api/v1/operations/**", async (route) => {
    const request = route.request();
    const path = new URL(request.url()).pathname;
    if (path.endsWith("/production")) return route.fulfill({ json: [batch] });
    if (path.endsWith("/production/1")) return route.fulfill({ json: batch });
    if (path.endsWith("/steps/1/reverse")) {
      expect(request.headers()["idempotency-key"]).toBeTruthy();
      expect(request.postDataJSON()).toEqual({
        note: "Remeasure",
        expected_created_at: stepTime,
      });
      batch.details.steps = [];
      return route.fulfill({ json: { id: 1 } });
    }
    if (path.endsWith("/internal-invoices"))
      return route.fulfill({ json: [invoice] });
    if (path.endsWith("/internal-invoices/2") && request.method() === "PATCH") {
      invoice.note = request.postDataJSON().note;
      return route.fulfill({ json: { id: 2 } });
    }
    if (path.endsWith("/internal-invoices/2/reverse")) {
      expect(request.headers()["idempotency-key"]).toBeTruthy();
      expect(request.postDataJSON()).toEqual({ note: "Entered twice" });
      invoice.is_reversed = true;
      return route.fulfill({ json: { id: 2 } });
    }
    return route.fallback();
  });
  await login(page);
  await page.getByLabel("Workspace", { exact: true }).selectOption("factory");
  await navigate(page, "Production");
  await page.getByRole("button", { name: "View", exact: true }).click();
  const production = page.getByRole("dialog", {
    name: "Production batch",
    exact: true,
  });
  const lastStep = production
    .locator("section.panel")
    .filter({
      has: page.getByRole("heading", { name: "1. Polishing", exact: true }),
    });
  const reverseStep = lastStep.getByRole("button", {
    name: "Reverse step",
    exact: true,
  });
  await reverseStep.click();
  await lastStep
    .getByRole("textbox", { name: "Reason / notes", exact: true })
    .fill("Remeasure");
  await reverseStep.click();
  await expect(
    production.getByRole("heading", { name: /Polishing/ }),
  ).toHaveCount(0);
  await production.getByRole("button", { name: "Close", exact: true }).click();

  await navigate(page, "Factory / Showroom account");
  const invoices = page.locator("section").filter({
    has: page.getByRole("heading", { name: "Internal invoices", exact: true }),
  });
  await invoices.getByRole("button", { name: "Edit", exact: true }).click();
  const edit = page.getByRole("dialog", { name: "Edit note", exact: true });
  await expect(
    edit.getByRole("textbox", { name: "Reason / notes" }),
  ).toHaveValue("Original note");
  await edit
    .getByRole("textbox", { name: "Reason / notes" })
    .fill("Corrected note");
  await edit.getByRole("button", { name: "Save", exact: true }).click();
  await expect(edit).toHaveCount(0);
  expect(invoice.note).toBe("Corrected note");
  await invoices.getByRole("button", { name: "Reverse", exact: true }).click();
  const reverse = page.getByRole("dialog", {
    name: "Reverse transaction",
    exact: true,
  });
  await reverse
    .getByRole("textbox", { name: "Reason / notes" })
    .fill("Entered twice");
  await reverse.getByRole("button", { name: "Reverse", exact: true }).click();
  await expect(
    invoices.getByRole("button", { name: "Reverse", exact: true }),
  ).toHaveCount(0);
});

test("factory batch reserves input, records mixed-purity steps and releases finished weight", async ({
  page,
}) => {
  await api(page);
  await page.route("**/api/v1/goldpurities?**", (route) =>
    route.fulfill({
      json: [
        { id: 1, name: "24K", karat: 24, purity: "99.5" },
        { id: 2, name: "18K", karat: 18, purity: "75" },
        { id: 3, name: "21K", karat: 21, purity: "87.5" },
      ],
      headers: { "X-Total-Count": "3" },
    }),
  );
  const batch = {
    id: 1,
    tracking_mode: "weight",
    status: "in_progress",
    reference: "B100",
    input_gold_24k: "100",
    output_gold_24k: "0",
    loss_gold_24k: "0",
    total_cost_usd: "5000",
    details: {
      inputs: [{ purity_id: 1, weight: "100", gold_24k: "100" }],
      steps: [] as Record<string, unknown>[],
    },
  };
  const writes: { path: string; body: Record<string, unknown> }[] = [];
  await page.route("**/api/v1/operations/**", async (route) => {
    const req = route.request(),
      path = new URL(req.url()).pathname;
    if (req.method() === "POST") {
      expect(req.headers()["x-business-unit"]).toBe("factory");
      expect(req.headers()["idempotency-key"]).toBeTruthy();
      const body = req.postDataJSON();
      writes.push({ path, body });
      if (path.endsWith("/steps")) {
        batch.details.steps.push({
          ...body,
          input_gold_24k: "100",
          output_gold_24k: "97.98995",
          loss_gold_24k: "2.01005",
        });
        batch.output_gold_24k = "97.98995";
        batch.loss_gold_24k = "2.01005";
      }
      if (path.endsWith("/finish")) batch.status = "active";
      return route.fulfill({
        status: 201,
        json: { id: 1, kind: "production", message: "Recorded" },
      });
    }
    if (path.endsWith("/production/1")) return route.fulfill({ json: batch });
    if (path.endsWith("/production"))
      return route.fulfill({
        json: [batch],
        headers: { "X-Total-Count": "1" },
      });
    await route.fallback();
  });
  await login(page);
  await page.getByLabel("Workspace", { exact: true }).selectOption("factory");
  await navigate(page, "Production");
  await page
    .getByRole("button", { name: "Start production", exact: true })
    .click();
  const start = page.getByRole("dialog", {
    name: "Start production",
    exact: true,
  });
  await start.getByLabel("Location", { exact: true }).selectOption("1");
  await start.getByLabel("Reference", { exact: true }).fill("B100");
  await start.getByLabel("Purity", { exact: true }).selectOption("1");
  await start.getByLabel("Weight (g)", { exact: true }).fill("100");
  await expect(start.getByLabel("Product", { exact: true })).toHaveCount(0);
  await start
    .getByRole("button", { name: "Start production", exact: true })
    .click();
  const detail = page.getByRole("dialog", {
    name: "Production batch",
    exact: true,
  });
  await detail.getByLabel("Step name", { exact: true }).fill("Alloying");
  await detail
    .getByLabel("Reason / notes", { exact: true })
    .first()
    .fill("Measured alloying loss");
  await detail.getByLabel("Purity", { exact: true }).selectOption("2");
  await detail.getByLabel("Weight (g)", { exact: true }).fill("60");
  await detail
    .getByRole("button", { name: "Add purity", exact: true })
    .first()
    .click();
  await detail.getByLabel("Purity", { exact: true }).nth(1).selectOption("3");
  await detail.getByLabel("Weight (g)", { exact: true }).nth(1).fill("60");
  await detail.getByRole("button", { name: "Save step", exact: true }).click();
  await expect(
    detail.getByRole("heading", { name: "1. Alloying", exact: true }),
  ).toBeVisible();
  await expect(
    detail.getByText("2.01005", { exact: true }).first(),
  ).toBeVisible();
  expect(writes[1].body).toMatchObject({
    expected_step: 0,
    name: "Alloying",
    outputs: [
      { purity_id: 2, weight: "60" },
      { purity_id: 3, weight: "60" },
    ],
    scrap: [],
  });
  await detail
    .getByRole("button", { name: "Finish production", exact: true })
    .click();
  await expect(
    detail.getByRole("button", { name: "Save step", exact: true }),
  ).toHaveCount(0);
  expect(writes[2].body).toEqual({ expected_step: 1 });
});

test("supplier invoice uses purity totals and per-gram making instead of piece identifiers", async ({
  page,
}) => {
  await api(page);
  let body: Record<string, unknown> | undefined;
  await page.route(
    "**/api/v1/operations/supplier-weight-sales",
    async (route) => {
      body = route.request().postDataJSON();
      await route.fulfill({
        status: 201,
        json: { id: 1, kind: "supplier_weight_sale", message: "Recorded" },
      });
    },
  );
  await login(page);
  await page.getByLabel("Workspace", { exact: true }).selectOption("factory");
  await navigate(page, "Inventory");
  await expect(
    page.getByRole("heading", { name: "Factory gold inventory", exact: true }),
  ).toBeVisible();
  await expect(
    page.getByRole("heading", { name: "Raw bulk gold", exact: true }),
  ).toBeVisible();
  await expect(
    page.getByRole("heading", { name: "Finished gold", exact: true }),
  ).toBeVisible();
  await expect(
    page.getByRole("button", { name: "Items", exact: true }),
  ).toHaveCount(0);
  await navigate(page, "Sales");
  await page
    .getByRole("button", { name: "Sell to supplier", exact: true })
    .click();
  const dialog = page.getByRole("dialog", {
    name: "Sell to supplier",
    exact: true,
  });
  await dialog.getByLabel("Location", { exact: true }).selectOption("1");
  await dialog.getByLabel("Supplier", { exact: true }).selectOption("1");
  await dialog.getByLabel("Purity", { exact: true }).selectOption("1");
  await dialog.getByLabel("Weight (g)", { exact: true }).fill("100");
  await dialog
    .getByLabel("Making charge / gram (USD)", { exact: true })
    .fill("2.50");
  await expect(dialog.getByLabel("Piece", { exact: true })).toHaveCount(0);
  await dialog.getByRole("button", { name: "Confirm", exact: true }).click();
  await expect(dialog).toHaveCount(0);
  expect(body).toMatchObject({
    location_id: 1,
    supplier_id: 1,
    lines: [{ purity_id: 1, weight: "100", making_per_gram: "2.50" }],
  });
  expect(body).not.toHaveProperty("pieces");
});

test("showroom registers received weight as individual pieces with photo input", async ({
  page,
}) => {
  await api(page);
  let pending = [
    { id: 1, invoice_id: 17, purity_id: 1, remaining_weight: "10" },
  ];
  let body: Record<string, unknown> | undefined;
  await page.route("**/api/v1/operations/pending-receipts", (route) =>
    route.fulfill({ json: pending }),
  );
  const photoToken = "a".repeat(32);
  await page.route(
    "**/api/v1/operations/weight-internal-invoices/17/photos",
    async (route) => {
      expect(route.request().headers()["x-business-unit"]).toBe("showroom");
      expect(route.request().method()).toBe("POST");
      expect(route.request().headers()["content-type"]).toBe("image/jpeg");
      const uploaded = route.request().postDataBuffer()!;
      expect(uploaded.subarray(0, 2).toString("hex")).toBe("ffd8");
      expect(uploaded.length).toBeLessThanOrEqual(10 * 1024 * 1024);
      await route.fulfill({
        status: 201,
        json: {
          token: photoToken,
          image_url: "/api/v1/media/items/receipt.jpg",
        },
      });
    },
  );
  await page.route(
    "**/api/v1/operations/weight-internal-invoices/17/receive",
    async (route) => {
      body = route.request().postDataJSON();
      expect(route.request().headers()["x-business-unit"]).toBe("showroom");
      expect(route.request().headers()["idempotency-key"]).toBeTruthy();
      pending = [];
      await route.fulfill({
        status: 201,
        json: {
          id: 17,
          kind: "showroom_receipt",
          inventory_item_ids: [1, 2],
          message: "Recorded",
        },
      });
    },
  );
  await login(page);
  await navigate(page, "Inventory");
  await page
    .getByRole("button", { name: "Register received pieces", exact: true })
    .click();
  const dialog = page.getByRole("dialog", {
    name: "Register received pieces",
    exact: true,
  });
  await dialog.getByLabel("Product", { exact: true }).selectOption("1");
  await dialog.getByLabel("Weight (g)", { exact: true }).fill("4");
  await expect(dialog.locator('input[type="file"]')).toHaveAttribute(
    "capture",
    "environment",
  );
  await dialog.locator('input[type="file"]').setInputFiles({
    name: "received-piece.png",
    mimeType: "image/png",
    buffer: Buffer.from(
      "iVBORw0KGgoAAAANSUhEUgAAAAIAAAACCAIAAAD91JpzAAAAFklEQVR4nGM8sTSCgYGBiYGBgYGBAQAV1gHJGLdvLgAAAABJRU5ErkJggg==",
      "base64",
    ),
  });
  await expect(
    dialog.getByText("Photo attached", { exact: true }),
  ).toBeVisible();
  await dialog.getByRole("button", { name: "Add piece", exact: true }).click();
  await dialog.getByLabel("Product", { exact: true }).nth(1).selectOption("1");
  await dialog.getByLabel("Weight (g)", { exact: true }).nth(1).fill("6");
  await dialog
    .getByRole("button", { name: "Register received pieces", exact: true })
    .click();
  await expect(dialog).toHaveCount(0);
  expect(body).toEqual({
    pieces: [
      { product_id: 1, weight: "4", photo_token: photoToken },
      { product_id: 1, weight: "6" },
    ],
  });
  await expect(
    page.getByRole("heading", {
      name: "Factory stock awaiting piece registration",
      exact: true,
    }),
  ).toHaveCount(0);
});
