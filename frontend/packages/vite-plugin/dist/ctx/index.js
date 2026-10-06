"use strict";
var __importDefault = (this && this.__importDefault) || function (mod) {
    return (mod && mod.__esModule) ? mod : { "default": mod };
};
Object.defineProperty(exports, "__esModule", { value: true });
exports.createCtx = createCtx;
const path_1 = require("path");
const utils_1 = require("../utils");
const glob_1 = require("glob");
const lodash_1 = require("lodash");
const config_1 = require("../config");
const fs_1 = __importDefault(require("fs"));
const axios_1 = __importDefault(require("axios"));
const node_util_1 = __importDefault(require("node:util"));
async function createCtx() {
    let ctx = {
        serviceLang: "Node",
    };
    if (config_1.config.type == "app" || config_1.config.type == "uniapp-x") {
        const manifest = (0, utils_1.readFile)((0, utils_1.rootDir)("manifest.json"), true);
        // 文件路径
        const ctxPath = (0, utils_1.rootDir)("pages.json");
        // 页面配置
        ctx = (0, utils_1.readFile)(ctxPath, true);
        // 原数据，做更新比较用
        const ctxData = (0, lodash_1.cloneDeep)(ctx);
        // 删除临时页面
        ctx.pages = ctx.pages?.filter((e) => !e.isTemp);
        ctx.subPackages = ctx.subPackages?.filter((e) => !e.isTemp);
        // 删除不需要的数据
        for (const i in ctx) {
            if (!["pages", "subPackages", "tabBar", "globalStyle", "uniIdRouter"].includes(i)) {
                delete ctx[i];
            }
        }
        // 加载 uni_modules 配置文件
        const files = await (0, glob_1.glob)((0, utils_1.rootDir)("uni_modules") + "/**/pages_init.json", {
            stat: true,
            withFileTypes: true,
        });
        for (const file of files) {
            if (file.isFile()) {
                const { pages = [], subPackages = [] } = (0, utils_1.readFile)((0, path_1.join)(file.path, file.name), true);
                // 合并到 pages 中
                [...pages, ...subPackages].forEach((e) => {
                    e.isTemp = true;
                    const isSub = !!e.root;
                    const d = isSub
                        ? ctx.subPackages?.find((a) => a.root == e.root)
                        : ctx.pages?.find((a) => a.path == e.path);
                    if (d) {
                        (0, lodash_1.assign)(d, e);
                    }
                    else {
                        if (isSub) {
                            ctx.subPackages?.unshift(e);
                        }
                        else {
                            ctx.pages?.unshift(e);
                        }
                    }
                });
            }
        }
        // 排序后检测，避免加载顺序问题
        function order(d) {
            return {
                pages: (0, lodash_1.orderBy)(d.pages, "path"),
                subPackages: (0, lodash_1.orderBy)(d.subPackages, "root"),
            };
        }
        // 是否需要更新 pages.json
        if (!node_util_1.default.isDeepStrictEqual(order(ctxData), order(ctx))) {
            console.log("[cool-ctx] pages updated");
            (0, utils_1.writeFile)(ctxPath, JSON.stringify(ctx, null, 4));
        }
        // appid
        ctx.appid = manifest.appid;
    }
    if (config_1.config.type == "admin") {
        const list = fs_1.default.readdirSync((0, utils_1.rootDir)("./src/modules"));
        ctx.modules = list.filter((e) => !e.includes("."));
        await axios_1.default
            .get(config_1.config.reqUrl + "/admin/base/comm/program", {
            timeout: 5000,
        })
            .then((res) => {
            const { code, data, message } = res.data;
            if (code === 1000) {
                ctx.serviceLang = data || "Node";
            }
            else {
                (0, utils_1.error)(`[cool-ctx] ${message}`);
            }
        })
            .catch((err) => {
            // console.error(['[cool-ctx] ', err.message])
        });
    }
    return ctx;
}
