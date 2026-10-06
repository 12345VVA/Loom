"use strict";
Object.defineProperty(exports, "__esModule", { value: true });
exports.base = base;
const eps_1 = require("./eps");
const utils_1 = require("./utils");
const plugin_1 = require("./plugin");
const proxy_1 = require("./proxy");
const file_1 = require("./file");
const config_1 = require("./config");
const tag_1 = require("./tag");
function base() {
    return {
        name: "vite-cool-base",
        enforce: "pre",
        configureServer(server) {
            server.middlewares.use(async (req, res, next) => {
                function done(data) {
                    res.writeHead(200, { "Content-Type": "text/html;charset=UTF-8" });
                    res.end(JSON.stringify(data));
                }
                if (req.originalUrl?.includes("__cool")) {
                    const body = await (0, utils_1.parseJson)(req);
                    switch (req.url) {
                        // 创建文件
                        case "/__cool_createFile":
                            await (0, file_1.createFile)(body);
                            break;
                        // 创建 eps 文件
                        case "/__cool_eps":
                            await (0, eps_1.createEps)();
                            break;
                        // 更新插件
                        case "/__cool_updatePlugin":
                            await (0, plugin_1.updatePlugin)(body);
                            break;
                        // 设置代理
                        case "/__cool_updateProxy":
                            await (0, proxy_1.updateProxy)(body);
                            break;
                        default:
                            return done({
                                code: 1001,
                                message: "Unknown request",
                            });
                    }
                    done({
                        code: 1000,
                    });
                }
                else {
                    next();
                }
            });
        },
        transform(code, id) {
            if (config_1.config.nameTag) {
                return (0, tag_1.createTag)(code, id);
            }
            return code;
        },
    };
}
