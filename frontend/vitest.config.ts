import { fileURLToPath, URL } from 'node:url';
import { defineConfig } from 'vitest/config';
import vue from '@vitejs/plugin-vue';
import vueJsx from '@vitejs/plugin-vue-jsx';

function toPath(dir: string) {
	return fileURLToPath(new URL(dir, import.meta.url));
}

function virtualMockPlugin() {
	return {
		name: 'virtual-mock-plugin',
		resolveId(id: string) {
			if (id === 'virtual:svg-register' || id === '@intlify/unplugin-vue-i18n/messages') {
				return id;
			}
		},
		load(id: string) {
			if (id === 'virtual:svg-register') return 'export default {}';
			if (id === '@intlify/unplugin-vue-i18n/messages') return 'export default {}';
		}
	};
}

export default defineConfig({
	plugins: [vue(), vueJsx(), virtualMockPlugin()],
	resolve: {
		alias: {
			'@intlify/unplugin-vue-i18n/messages': toPath('./tests/mocks/empty.ts'),
			'virtual:svg-register': toPath('./tests/mocks/empty.ts'),
			'/@': toPath('./src'),
			'/$': toPath('./src/modules'),
			'/#': toPath('./src/plugins'),
			'/~': toPath('./packages')
		}
	},
	test: {
		environment: 'jsdom',
		globals: true,
		setupFiles: ['./tests/setup.ts'],
		include: ['tests/unit/**/*.test.ts'],
		coverage: {
			provider: 'v8',
			reporter: ['text', 'html'],
			reportsDirectory: './coverage',
			include: [
				'src/cool/service/**/*.ts',
				'src/cool/utils/**/*.ts',
				'src/modules/base/store/**/*.ts',
				'src/modules/base/utils/**/*.ts',
				'src/modules/dict/store/**/*.ts',
				'src/modules/dict/utils/**/*.ts',
				'src/modules/workflow/composables/**/*.ts',
				'src/modules/workflow/utils/**/*.ts'
			],
			exclude: [
				'**/*.d.ts',
				'**/index.ts',
				'**/*.config.*',
				'**/dist/**',
				'**/demo/**',
				'**/*.vue'
			]
		}
	}
});
