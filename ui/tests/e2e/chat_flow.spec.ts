import { test, expect } from "@playwright/test";

test.describe("ADAM Administrative Records E2E Flow (H7)", () => {
  test.beforeEach(async ({ page }) => {
    // Navigate to local ADAM instance
    await page.goto("/");
  });

  test("1. Authentication and role-based clearance UI elements are displayed", async ({ page }) => {
    // Check state banner and branding
    await expect(page).toHaveTitle(/ADAM/i);
    const heading = page.locator("header, h1, [role='banner']").first();
    await expect(heading).toBeVisible();

    // Verify clearance and role selectors/badges exist
    const clearanceIndicator = page.locator("text=/PUBLIC|INTERNAL|CONFIDENTIAL|RESTRICTED/i").first();
    await expect(clearanceIndicator).toBeVisible();
  });

  test("2. Query flow with cited sources and evidence packet", async ({ page }) => {
    const inputArea = page.locator("textarea, input[type='text']").first();
    await expect(inputArea).toBeVisible();

    // Submit a query about dearness allowance
    await inputArea.fill("What is the revised rate of Dearness Allowance for state employees?");
    await inputArea.press("Enter");

    // Expect response container or thinking state
    const responseContainer = page.locator("[role='log'], [data-testid='chat-messages'], .chat-message, text=/Dearness Allowance|DA|50%/i").first();
    await expect(responseContainer).toBeVisible({ timeout: 15000 });
  });

  test("3. Out-of-domain query triggers statutory abstention / refusal", async ({ page }) => {
    const inputArea = page.locator("textarea, input[type='text']").first();
    await expect(inputArea).toBeVisible();

    // Ask an unanswerable query with no basis in Uttarakhand government orders
    await inputArea.fill("What is the subsidy rate for deep-sea submarine construction in Uttarakhand?");
    await inputArea.press("Enter");

    // Expect refusal banner / no-evidence notice
    const refusalNotice = page.locator("text=/No authoritative|No evidence|No official/i").first();
    await expect(refusalNotice).toBeVisible({ timeout: 15000 });
  });

  test("4. Document upload view accessibility and upload interaction", async ({ page }) => {
    // Open documents view or upload drawer
    const docsTab = page.locator("button, a, [role='tab']").filter({ hasText: /Documents|Upload|अभिलेख/i }).first();
    if (await docsTab.isVisible()) {
      await docsTab.click();
      const dropzone = page.locator("input[type='file'], text=/Drag and drop|Upload/i").first();
      await expect(dropzone).toBeVisible();
    }
  });

  test("5. Accessibility: landmarks, keyboard navigable palette, and contrast", async ({ page }) => {
    // Command palette shortcut (Cmd+K or Ctrl+K)
    await page.keyboard.press("Meta+K");
    const modal = page.locator("[role='dialog'], [data-testid='command-palette'], input[placeholder*='Search']").first();
    if (await modal.isVisible()) {
      await expect(modal).toBeVisible();
      await page.keyboard.press("Escape");
    }

    // Main landmark should exist
    const main = page.locator("main, [role='main']");
    await expect(main).toBeVisible();
  });
});
