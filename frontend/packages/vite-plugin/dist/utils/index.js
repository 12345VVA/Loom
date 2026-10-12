"use strict";
var __importDefault = (this && this.__importDefault) || function (mod) {
    return (mod && mod.__esModule) ? mod : { "default": mod };
};
Object.defineProperty(exports, "__esModule", { value: true });
exports.rootDir = rootDir;
exports.firstUpperCase = firstUpperCase;
exports.toCamel = toCamel;
exports.createDir = createDir;
exports.readFile = readFile;
exports.writeFile = writeFile;
exports.writeFileAtomic = writeFileAtomic;
exports.parseJson = parseJson;
exports.formatContent = formatContent;
exports.error = error;
exports.success = success;
exports.compareVersion = compareVersion;
const fs_1 = __importDefault(require("fs"));
const path_1 = require("path");
const config_1 = require("../config");
const prettier_1 = __importDefault(require("prettier"));
// 根目录
function rootDir(path) {
    switch (config_1.config.type) {
        case "app":
        case "uniapp-x":
            return (0, path_1.join)(process.env.UNI_INPUT_DIR, path);
        default:
            return (0, path_1.join)(process.cwd(), path);
    }
}
// 首字母大写
function firstUpperCase(value) {
    return value.replace(/\b(\w)(\w*)/g, function ($0, $1, $2) {
        return $1.toUpperCase() + $2;
    });
}
// 横杠转驼峰
function toCamel(str) {
    return str.replace(/([^-])(?:-+([^-]))/g, function ($0, $1, $2) {
        return $1 + $2.toUpperCase();
    });
}
// 创建目录
function createDir(path, recursive) {
    try {
        if (!fs_1.default.existsSync(path))
            fs_1.default.mkdirSync(path, { recursive });
    }
    catch (err) { }
}
// 读取文件
function readFile(path, json) {
    try {
        const content = fs_1.default.readFileSync(path, "utf8");
        return json ? JSON.parse(removeJsonComments(content)) : content;
    }
    catch (err) { }
    return "";
}
// 安全地移除JSON中的注释
function removeJsonComments(content) {
    let result = "";
    let inString = false;
    let stringChar = "";
    let escaped = false;
    let i = 0;
    while (i < content.length) {
        const char = content[i];
        const nextChar = content[i + 1];
        // 处理字符串状态
        if (!inString && (char === '"' || char === "'")) {
            inString = true;
            stringChar = char;
            result += char;
        }
        else if (inString && char === stringChar && !escaped) {
            inString = false;
            stringChar = "";
            result += char;
        }
        else if (inString) {
            // 在字符串内，直接添加字符
            result += char;
            escaped = char === "\\" && !escaped;
        }
        else {
            // 不在字符串内，检查注释
            if (char === "/" && nextChar === "/") {
                // 单行注释，跳过到行尾
                while (i < content.length && content[i] !== "\n") {
                    i++;
                }
                if (i < content.length) {
                    result += content[i]; // 保留换行符
                }
            }
            else if (char === "/" && nextChar === "*") {
                // 多行注释，跳过到 */
                i += 2;
                while (i < content.length - 1) {
                    if (content[i] === "*" && content[i + 1] === "/") {
                        i += 2;
                        break;
                    }
                    i++;
                }
                continue;
            }
            else {
                result += char;
                escaped = false;
            }
        }
        i++;
    }
    return result;
}
// 写入文件
function writeFile(path, data) {
    try {
        return fs_1.default.writeFileSync(path, data);
    }
    catch (err) { }
    return "";
}
// 原子写入：临时文件(唯一命名+同目录保证同卷) + rename 覆盖。
// 防两类历史事故：createWriteStream 裸写不等 flush 的部分内容落盘、
// 多 vite 进程并发写同一目标文件互相截断（06f07c1 曾修过一次文件损坏）。
// Windows 上目标被杀毒/索引器短暂占用时 rename 会 EPERM——不静默：
// 打印目标路径后跳过，等下次触发（HMR/重启）重写。
function writeFileAtomic(path, data) {
    const tmp = (0, path_1.join)((0, path_1.dirname)(path), `.${(0, path_1.basename)(path)}.tmp-${process.pid}-${Math.random().toString(36).slice(2, 8)}`);
    try {
        fs_1.default.writeFileSync(tmp, data);
        fs_1.default.renameSync(tmp, path);
    }
    catch (err) {
        try {
            fs_1.default.unlinkSync(tmp);
        }
        catch { }
        error(`[cool-eps] Atomic write failed (skipped, retry on next trigger): ${path} → ${err?.message || err}`);
    }
}
// 解析body
function parseJson(req) {
    return new Promise((resolve) => {
        let d = "";
        req.on("data", function (chunk) {
            d += chunk;
        });
        req.on("end", function () {
            try {
                resolve(JSON.parse(d));
            }
            catch {
                resolve({});
            }
        });
    });
}
// 格式化内容
function formatContent(content, options) {
    return prettier_1.default.format(content, {
        parser: "typescript",
        useTabs: true,
        tabWidth: 4,
        endOfLine: "lf",
        semi: true,
        ...options,
    });
}
function error(message) {
    console.log("\x1B[31m%s\x1B[0m", message);
}
function success(message) {
    console.log("\x1B[32m%s\x1B[0m", message);
}
/**
 * 比较两个版本号
 * @param version1 版本号1 (如: "1.2.3")
 * @param version2 版本号2 (如: "1.2.4")
 * @returns 1: version1 > version2, 0: 相等, -1: version1 < version2
 */
function compareVersion(version1, version2) {
    const v1Parts = version1.split(".").map(Number);
    const v2Parts = version2.split(".").map(Number);
    const maxLength = Math.max(v1Parts.length, v2Parts.length);
    for (let i = 0; i < maxLength; i++) {
        const v1Part = v1Parts[i] || 0;
        const v2Part = v2Parts[i] || 0;
        if (v1Part > v2Part)
            return 1;
        if (v1Part < v2Part)
            return -1;
    }
    return 0;
}
