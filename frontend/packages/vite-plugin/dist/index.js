"use strict";
Object.defineProperty(exports, "__esModule", { value: true });
exports.cool = cool;
const base_1 = require("./base");
const config_1 = require("./config");
const demo_1 = require("./demo");
const proxy_1 = require("./proxy");
const virtual_1 = require("./virtual");
const lodash_1 = require("lodash");
const uniapp_x_1 = require("./uniapp-x");
function cool(options) {
    // 应用类型，admin | app
    config_1.config.type = options.type;
    // 请求地址
    config_1.config.reqUrl = (0, proxy_1.getProxyTarget)(options.proxy);
    if (config_1.config.type == "uniapp-x") {
        // 编译平台
        config_1.config.utsPlatform = process.env.UNI_UTS_PLATFORM ?? "web";
        // 是否纯净版
        config_1.config.clean = options.clean ?? true;
        if (config_1.config.clean) {
            // 默认设置为测试地址
            config_1.config.reqUrl = "https://show.cool-admin.com/api";
        }
    }
    // 是否开启名称标签
    config_1.config.nameTag = options.nameTag ?? true;
    // svg
    if (options.svg) {
        (0, lodash_1.assign)(config_1.config.svg, options.svg);
    }
    // Eps
    if (options.eps) {
        const { dist, mapping, api, enable = true } = options.eps;
        // 是否开启
        config_1.config.eps.enable = enable;
        // 类型
        if (api) {
            config_1.config.eps.api = api;
        }
        // 输出目录
        if (dist) {
            config_1.config.eps.dist = dist;
        }
        // 匹配规则
        if (mapping) {
            (0, lodash_1.merge)(config_1.config.eps.mapping, mapping);
        }
    }
    // 如果类型为 uniapp-x，则关闭 eps
    if (config_1.config.type == "uniapp-x") {
        config_1.config.eps.enable = false;
    }
    // uniapp
    if (options.uniapp) {
        (0, lodash_1.assign)(config_1.config.uniapp, options.uniapp);
    }
    // tailwind
    if (options.tailwind) {
        (0, lodash_1.assign)(config_1.config.tailwind, options.tailwind);
    }
    return [(0, base_1.base)(), (0, virtual_1.virtual)(), (0, uniapp_x_1.uniappX)(), (0, demo_1.demo)(options.demo)];
}
