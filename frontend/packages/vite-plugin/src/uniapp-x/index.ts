import type { Plugin } from "vite";
import { config } from "../config";
import { tailwindPlugin } from "./tailwind";
import { codePlugin } from "./code";

/**
 * uniappX 入口，自动注入 Tailwind 类名转换插件
 * @param options 配置项
 * @returns Vite 插件数组
 */
export async function uniappX() {
	const plugins: Plugin[] = [];

	if (config.type == "uniapp-x") {
		plugins.push(...codePlugin());

		if (config.tailwind.enable) {
			plugins.push(...tailwindPlugin());
		}
	}

	return plugins;
}
