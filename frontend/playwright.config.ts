import { defineConfig, devices } from '@playwright/test';

const baseURL = process.env.PLAYWRIGHT_BASE_URL || 'http://127.0.0.1:9090';

export default defineConfig({
	testDir: './tests/e2e',
	timeout: 30_000,
	expect: {
		timeout: 5_000
	},
	fullyParallel: false,
	retries: process.env.CI ? 1 : 0,
	reporter: process.env.CI ? 'github' : 'list',
	use: {
		baseURL,
		trace: 'on-first-retry'
	},
	webServer: process.env.PLAYWRIGHT_SKIP_WEB_SERVER
		? undefined
		: {
				command: 'npm run dev -- --host 127.0.0.1',
				url: baseURL,
				reuseExistingServer: !process.env.CI,
				timeout: 120_000
			},
	projects: [
		{
			name: 'chromium',
			use: { ...devices['Desktop Chrome'] }
		}
	]
});
