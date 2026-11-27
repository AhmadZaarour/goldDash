import { expect, test } from "@playwright/test";
import { api } from "./helpers";

test("a username can sign in through the same field as an email", async ({
  page,
}) => {
  await api(page);
  await page.route("**/api/v1/auth/login", async (route) => {
    const payload = route.request().postDataJSON();
    expect(payload.identifier).toBe("Ahmad");
    expect(payload).not.toHaveProperty("email");
    if (payload.password !== "TestPassword123!") {
      return route.fulfill({
        status: 401,
        json: { detail: "Invalid username, email or password" },
      });
    }
    return route.fallback();
  });

  await page.goto("/");
  await page.getByLabel("Username or email", { exact: true }).fill("Ahmad");
  const password = page.getByLabel("Password", { exact: true });
  const signIn = page.getByRole("button", { name: "Sign in", exact: true });
  await password.fill("wrong-password");
  await signIn.click();
  await expect(page.getByRole("alert")).toContainText(
    "Invalid username, email or password",
  );
  await password.fill("TestPassword123!");
  await signIn.click();
  await expect(
    page.getByRole("heading", { name: "Overview", exact: true }),
  ).toBeVisible();
});
