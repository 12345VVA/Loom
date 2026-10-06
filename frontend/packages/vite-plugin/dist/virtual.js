"use strict";
Object.defineProperty(exports, "__esModule", { value: true });
exports.virtual = virtual;
const eps_1 = require("./eps");
const ctx_1 = require("./ctx");
const svg_1 = require("./svg");
async function virtual() {
    const virtualModuleIds = [
        "virtual:eps",
        "virtual:ctx",
        "virtual:svg-register",
        "virtual:svg-icons",
    ];
    /**
     * 剥离 dts（运行时只用 path/method/search），避免 EPS 元数据撑大产物
     */
    function slimEps(data) {
        return JSON.parse(JSON.stringify(data, (key, value) => (key === "dts" ? undefined : value)));
    }
    (0, eps_1.createEps)();
    return {
        name: "vite-cool-virtual",
        enforce: "pre",
        configureServer(server) {
            server.middlewares.use(async (req, res, next) => {
                // 页面刷新时触发
                if (req.url == "/@vite/client") {
                    // 重新加载虚拟模块
                    virtualModuleIds.forEach((vm) => {
                        const mod = server.moduleGraph.getModuleById(`\0${vm}`);
                        if (mod) {
                            server.moduleGraph.invalidateModule(mod);
                        }
                    });
                }
                next();
            });
        },
        handleHotUpdate({ file, server }) {
            // 文件修改时触发
            if (!["pages.json", "dist", "build/cool", "eps.json", "eps.d.ts"].some((e) => file.includes(e))) {
                (0, ctx_1.createCtx)();
                (0, eps_1.createEps)().then((data) => {
                    if (data.isUpdate) {
                        // 通知客户端刷新
                        (server.hot || server.ws).send({
                            type: "custom",
                            event: "eps-update",
                            data: slimEps(data),
                        });
                    }
                });
            }
        },
        resolveId(id) {
            if (virtualModuleIds.includes(id)) {
                return "\0" + id;
            }
        },
        async load(id) {
            if (id === "\0virtual:eps") {
                const eps = await (0, eps_1.createEps)();
                return `
					export const eps = ${JSON.stringify(slimEps(eps))}
				`;
            }
            if (id === "\0virtual:ctx") {
                const ctx = await (0, ctx_1.createCtx)();
                return `
					export const ctx = ${JSON.stringify(ctx)}
				`;
            }
            if (id == "\0virtual:svg-register") {
                const { code } = await (0, svg_1.createSvg)();
                return code;
            }
            if (id == "\0virtual:svg-icons") {
                const { svgIcons } = await (0, svg_1.createSvg)();
                return `
					export const svgIcons = ${JSON.stringify(svgIcons)}
				`;
            }
        },
    };
}
