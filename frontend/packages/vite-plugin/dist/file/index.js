"use strict";
Object.defineProperty(exports, "__esModule", { value: true });
exports.createFile = createFile;
const fs_1 = require("fs");
const path_1 = require("path");
const utils_1 = require("../utils");
const lodash_1 = require("lodash");
// 创建文件
async function createFile(data) {
    const list = (0, lodash_1.isArray)(data) ? data : [data];
    for (const item of list) {
        const { path, code } = item;
        // 格式化内容
        const content = await (0, utils_1.formatContent)(code, {
            parser: "vue",
        });
        // 目录路径
        const dir = (path || "").split("/");
        // 文件名
        const fname = dir.pop();
        // 源码路径
        const srcPath = `./src/${dir.join("/")}`;
        // 创建目录
        (0, utils_1.createDir)(srcPath, true);
        // 创建文件
        (0, fs_1.createWriteStream)((0, path_1.join)(srcPath, fname), {
            flags: "w",
        }).write(content);
    }
}
