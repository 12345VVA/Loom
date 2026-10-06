import type { Plugin } from "vite";
/**
 * 转换类名中的特殊字符为安全字符
 */
export declare function toSafeClass(className: string): string;
/**
 * Tailwind 类名转换插件
 */
export declare function tailwindPlugin(): Plugin<any>[];
