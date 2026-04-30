import { test, expect } from '@playwright/test';

test('renders the login page', async ({ page }) => {
	await page.goto('/login');
	await expect(page).toHaveURL(/\/login/);
	await expect(page.locator('input').first()).toBeVisible();
});
