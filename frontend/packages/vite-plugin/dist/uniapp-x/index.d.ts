import type { Plugin } from "vite";
/**
 * uniappX 入口，自动注入 Tailwind 类名转换插件
 * @param options 配置项
 * @returns Vite 插件数组
 */
export declare function uniappX(): Promise<Plugin<any>[]>;
