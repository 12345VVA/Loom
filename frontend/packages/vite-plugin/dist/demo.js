"use strict";
var __importDefault = (this && this.__importDefault) || function (mod) {
    return (mod && mod.__esModule) ? mod : { "default": mod };
};
Object.defineProperty(exports, "__esModule", { value: true });
exports.demo = demo;
const glob_1 = require("glob");
const path_1 = __importDefault(require("path"));
const fs_1 = require("fs");
const utils_1 = require("./utils");
function demo(enable) {
    const virtualModuleIds = ["virtual:demo"];
    return {
        name: "vite-cool-demo",
        enforce: "pre",
        resolveId(id) {
            if (virtualModuleIds.includes(id)) {
                return "\0" + id;
            }
        },
        async load(id) {
            if (id === "\0virtual:demo") {
                const demo = {};
                if (enable) {
                    const files = await (0, glob_1.glob)((0, utils_1.rootDir)("./src/modules/demo/views/crud/components") + "/**", {
                        stat: true,
                        withFileTypes: true,
                    });
                    for (const file of files) {
                        if (file.isFile()) {
                            const p = path_1.default.join(file.path, file.name);
                            demo[p
                                .replace(/\\/g, "/")
                                .split("src/modules/demo/views/crud/components/")[1]] = (0, fs_1.readFileSync)(p, "utf-8");
                        }
                    }
                }
                return `
					export const demo = ${JSON.stringify(demo)};
				`;
            }
        },
    };
}
