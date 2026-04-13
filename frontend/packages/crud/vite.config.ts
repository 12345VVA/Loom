import { defineConfig } from "vite";
import vue from "@vitejs/plugin-vue";
import vueJsx from "@vitejs/plugin-vue-jsx";
import dts from "vite-plugin-dts";
import { resolve } from "path";

// https://vitejs.dev/config/
export default defineConfig({
	plugins: [
		vue(),
		vueJsx(),
		dts({
			include: ["src/**/*.ts", "src/**/*.tsx", "src/**/*.vue"],
			outDir: "types"
		})
	],

	css: {
		preprocessorOptions: {
			scss: {
				charset: false,
				api: "modern-compiler"
			}
		}
	},

	build: {
		lib: {
			entry: resolve(__dirname, "src/entry.ts"),
			name: "index",
			fileName: (format) => `index.${format}.js`,
			cssFileName: "index"
		},
		rollupOptions: {
			external: ["element-plus", "@element-plus/icons-vue", "vue"],
			output: {
				exports: "named",
				globals: {
					"element-plus": "ElementPlus",
					"@element-plus/icons-vue": "ElementPlusIconsVue",
					vue: "Vue"
				}
			}
		},
		sourcemap: true,
		minify: "terser",
		cssCodeSplit: false
	}
});
