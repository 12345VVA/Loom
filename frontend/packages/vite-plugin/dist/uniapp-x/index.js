"use strict";
Object.defineProperty(exports, "__esModule", { value: true });
exports.uniappX = uniappX;
const config_1 = require("../config");
const tailwind_1 = require("./tailwind");
const code_1 = require("./code");
/**
 * uniappX 入口，自动注入 Tailwind 类名转换插件
 * @param options 配置项
 * @returns Vite 插件数组
 */
async function uniappX() {
    const plugins = [];
    if (config_1.config.type == "uniapp-x") {
        plugins.push(...(0, code_1.codePlugin)());
        if (config_1.config.tailwind.enable) {
            plugins.push(...(0, tailwind_1.tailwindPlugin)());
        }
    }
    return plugins;
}
