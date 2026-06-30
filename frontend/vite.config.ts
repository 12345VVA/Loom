import { fileURLToPath, URL } from 'node:url';
import { ConfigEnv, UserConfig } from 'vite';
import vue from '@vitejs/plugin-vue';
import vueJsx from '@vitejs/plugin-vue-jsx';
import compression from 'vite-plugin-compression';
import VueI18nPlugin from '@intlify/unplugin-vue-i18n/vite';
import vueDevTools from 'vite-plugin-vue-devtools';
import { visualizer } from 'rollup-plugin-visualizer';
import { proxy } from './src/config/proxy';
import { cool } from '@cool-vue/vite-plugin';

function toPath(dir: string) {
	return fileURLToPath(new URL(dir, import.meta.url));
}

// https://vitejs.dev/config
export default ({ mode }: ConfigEnv): UserConfig => {
	const isDev = mode === 'development';
	// bundle 分析模式：`npm run build:analyze` 触发，生成 dist/stats.html
	const enableAnalyze = mode === 'analyze';

	return {
		plugins: [
			vue(),
			compression(),
			vueJsx(),
			// vueDevTools(),
			cool({
				type: 'admin',
				proxy,
				eps: {
					enable: true
				},
				svg: {
					skipNames: ['base', 'theme']
				},
				demo: mode == 'demo' // 是否开启演示模式
			}),
			// bundle 分析：仅在 build:analyze 模式下注入 visualizer，不影响默认 build
			enableAnalyze &&
				visualizer({
					open: true,
					gzipSize: true,
					brotliSize: true,
					filename: 'dist/stats.html'
				}),
			VueI18nPlugin({
				include: [toPath('./src/{modules,plugins}/**/locales/**')]
			})
		],
		base: '/',
		server: {
			port: 9090,
			proxy,
			hmr: {
				overlay: true
			}
		},
		css: {
			preprocessorOptions: {
				scss: {
					charset: false,
					api: 'modern-compiler'
				}
			}
		},
		resolve: {
			alias: {
				'/@': toPath('./src'),
				'/$': toPath('./src/modules'),
				'/#': toPath('./src/plugins'),
				'/~': toPath('./packages')
			}
		},
		esbuild: {
			drop: isDev ? [] : ['console', 'debugger']
		},
		build: {
			minify: 'esbuild',
			// terserOptions: {
			// 	compress: {
			// 		drop_console: true,
			// 		drop_debugger: true
			// 	}
			// },
			sourcemap: isDev,
			rollupOptions: {
				output: {
					chunkFileNames: 'static/js/[name]-[hash].js',
					entryFileNames: 'static/js/[name]-[hash].js',
					assetFileNames: 'static/[ext]/[name]-[hash].[ext]',
					manualChunks(id) {
						if (id.includes('node_modules')) {
							if (!['@cool-vue/crud'].find(e => id.includes(e))) {
								if (id.includes('prettier')) {
									return;
								}

								return id
									.toString()
									.split('node_modules/')[1]
									.replace('.pnpm/', '')
									.split('/')[0];
							} else {
								return 'comm';
							}
						}
					}
				}
			}
		}
	};
};
