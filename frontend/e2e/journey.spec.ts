import { expect, test } from "@playwright/test";

// One user's full India-first journey against the real API with demo data.
test("research an Indian company end to end", async ({ page }) => {
  const email = `e2e-${Date.now()}@example.com`;

  await page.goto("/login");
  await page.getByRole("button", { name: "New here? Create an account" }).click();
  await page.getByLabel("Email").fill(email);
  await page.getByLabel(/Password/).fill("correct-horse-battery");
  await page.getByRole("button", { name: "Create account" }).click();

  // Search and pick the NSE listing of a dual-listed company.
  await page.getByLabel("Search companies").fill("demo infotech");
  await page.getByRole("link", { name: "Demo Infotech Ltd on NSE" }).click();
  await expect(page.getByRole("heading", { name: "Demo Infotech Ltd" })).toBeVisible();

  const quote = page.getByRole("region", { name: "Latest close" });
  await expect(quote.getByTestId("close-price")).toContainText("₹");
  await expect(quote.getByText("Demo data")).toBeVisible();
  await expect(quote.getByText(/Not a real-time quote/)).toBeVisible();

  // Switch to the BSE listing: a separate instrument.
  await page.getByRole("button", { name: "BSE: DEMOINFO" }).click();
  await expect(page).toHaveURL(/exchange=BSE/);
  await page.getByRole("button", { name: "NSE: DEMOINFO" }).click();

  // Fetch statements; consolidated / standalone are separate series.
  await page.getByRole("button", { name: "Fetch statements" }).click();
  const statements = page.getByRole("region", { name: "Financial statements" });
  await expect(statements.getByRole("table")).toContainText("₹12,000.00 Cr");
  await statements.getByRole("button", { name: "Standalone" }).click();
  await expect(statements.getByRole("table")).toContainText("₹8,400.00 Cr");
  await expect(page.getByRole("region", { name: "Ratios" })).toContainText("Return on capital employed");
  await expect(page.getByRole("region", { name: "Valuation multiples" })).toContainText("P/E");

  // DCF with the equity bridge prefilled from reported statements.
  await page.getByRole("link", { name: "Open valuation calculators" }).click();
  await expect(page.getByText(/prefilled from DEMOINFO's FY26/)).toBeVisible();
  await page.getByLabel("Free cash flow by year (₹ Cr)").fill("2000, 2200, 2400");
  await page.getByLabel("WACC").fill("12");
  await page.getByLabel("Terminal growth").fill("5");
  await page.getByRole("button", { name: "Run DCF" }).click();
  await expect(page.getByTestId("dcf-per-share")).toContainText("₹");
  await page.getByLabel("Save as").fill("E2E base case");
  await page.getByRole("button", { name: "Save valuation" }).click();
  await expect(page.getByText("Saved.")).toBeVisible();

  // Research report with provenance; AI is not configured in E2E and says so.
  await page.goto("/companies/DEMOINFO?exchange=NSE");
  await expect(page.getByText(/AI assistant is not configured/)).toBeVisible();
  await page.getByRole("button", { name: "Generate research report" }).click();
  await expect(page.getByRole("heading", { name: /research report/ })).toBeVisible();
  await expect(page.getByRole("region", { name: "Your saved DCF valuations" })).toContainText("E2E base case");
  await expect(page.getByRole("region", { name: "Ratios" })).toContainText("Calculated");
  await expect(page.getByText(/Unavailable: AI summary not requested/)).toBeVisible();

  const download = page.waitForEvent("download");
  await page.getByRole("button", { name: "Download Markdown" }).click();
  expect((await download).suggestedFilename()).toMatch(/^finsight-DEMOINFO-\d{8}\.md$/);
});
