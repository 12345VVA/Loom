"use strict";
Object.defineProperty(exports, "__esModule", { value: true });
exports.updateProxy = updateProxy;
exports.getProxyTarget = getProxyTarget;
const utils_1 = require("../utils");
const config_1 = require("../config");
function getPath() {
    return (0, utils_1.rootDir)(`.${config_1.config.type == "admin" ? "/src" : ""}/config/proxy.ts`);
}
async function updateProxy(data) {
    let code = (0, utils_1.readFile)(getPath());
    const regex = /const\s+value\s*=\s*['"]([^'"]+)['"]/;
    if (regex.test(code)) {
        code = code.replace(regex, `const value = '${data.name}'`);
    }
    (0, utils_1.writeFile)(getPath(), code);
}
function getProxyTarget(proxy) {
    const code = (0, utils_1.readFile)(getPath());
    const regex = /const\s+value\s*=\s*['"]([^'"]+)['"]/;
    const match = code.match(regex);
    if (match) {
        const value = match[1];
        try {
            const { target, rewrite } = proxy[`/${value}/`];
            return target + rewrite(`/${value}`);
        }
        catch (err) {
            (0, utils_1.error)(`[cool-proxy] Error：${value} → ` + getPath());
            return "";
        }
    }
}
