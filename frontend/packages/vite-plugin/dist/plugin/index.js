"use strict";
Object.defineProperty(exports, "__esModule", { value: true });
exports.updatePlugin = updatePlugin;
const utils_1 = require("../utils");
function getPlugin(name) {
    let code = (0, utils_1.readFile)((0, utils_1.rootDir)(`./src/plugins/${name}/config.ts`));
    // 设置插件配置
    const set = (key, value) => {
        const regex = new RegExp(`(return\\s*{[^}]*?\\b${key}\\b\\s*:\\s*)([^,}]+)`);
        if (regex.test(code)) {
            code = code.replace(regex, `$1${JSON.stringify(value)}`);
        }
        else {
            const insertPos = code.indexOf("return {") + 8;
            code =
                code.slice(0, insertPos) +
                    `\n  ${key}: ${JSON.stringify(value)},` +
                    code.slice(insertPos);
        }
    };
    // 保存插件配置
    const save = async () => {
        const content = await (0, utils_1.formatContent)(code);
        (0, utils_1.writeFile)((0, utils_1.rootDir)(`./src/plugins/${name}/config.ts`), content);
    };
    return {
        set,
        save,
    };
}
// 修改插件
async function updatePlugin(options) {
    const plugin = getPlugin(options.name);
    if (options.enable !== undefined) {
        plugin.set("enable", options.enable);
    }
    await plugin.save();
}
