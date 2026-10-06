"use strict";
var __importDefault = (this && this.__importDefault) || function (mod) {
    return (mod && mod.__esModule) ? mod : { "default": mod };
};
Object.defineProperty(exports, "__esModule", { value: true });
exports.createSvg = createSvg;
const fs_1 = require("fs");
const path_1 = require("path");
const utils_1 = require("../utils");
const svgo_1 = __importDefault(require("svgo"));
const config_1 = require("../config");
let svgIcons = [];
function findSvg(dir) {
    const arr = [];
    const dirs = (0, fs_1.readdirSync)(dir, {
        withFileTypes: true,
    });
    // 获取当前目录的模块名
    const moduleName = dir.match(/[/\\](?:src[/\\](?:plugins|modules)[/\\])([^/\\]+)/)?.[1] || "";
    for (const d of dirs) {
        if (d.isDirectory()) {
            arr.push(...findSvg(dir + d.name + "/"));
        }
        else {
            if ((0, path_1.extname)(d.name) == ".svg") {
                const baseName = (0, path_1.basename)(d.name, ".svg");
                // 判断是否需要跳过拼接模块名
                let shouldSkip = config_1.config.svg.skipNames?.includes(moduleName);
                // 跳过包含icon-
                if (baseName.includes("icon-")) {
                    shouldSkip = true;
                }
                const iconName = shouldSkip ? baseName : `${moduleName}-${baseName}`;
                svgIcons.push(iconName);
                const svg = (0, fs_1.readFileSync)(dir + d.name)
                    .toString()
                    .replace(/(\r)|(\n)/g, "")
                    .replace(/<svg([^>+].*?)>/, (_, $2) => {
                    let width = 0;
                    let height = 0;
                    let content = $2.replace(/(width|height)="([^>+].*?)"/g, (_, s2, s3) => {
                        if (s2 === "width") {
                            width = s3;
                        }
                        else if (s2 === "height") {
                            height = s3;
                        }
                        return "";
                    });
                    if (!/(viewBox="[^>+].*?")/g.test($2)) {
                        content += `viewBox="0 0 ${width} ${height}"`;
                    }
                    return `<symbol id="icon-${iconName}" ${content}>`;
                })
                    .replace("</svg>", "</symbol>");
                arr.push(svg);
            }
        }
    }
    return arr;
}
function compilerSvg() {
    svgIcons = [];
    return findSvg((0, utils_1.rootDir)("./src/"))
        .map((e) => {
        return svgo_1.default.optimize(e)?.data || e;
    })
        .join("");
}
async function createSvg() {
    const html = compilerSvg();
    const code = `
if (typeof window !== 'undefined') {
	function loadSvg() {
		const svgDom = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
		svgDom.style.position = 'absolute';
		svgDom.style.width = '0';
		svgDom.style.height = '0';
		svgDom.setAttribute('xmlns','http://www.w3.org/2000/svg');
		svgDom.setAttribute('xmlns:link','http://www.w3.org/1999/xlink');
		svgDom.innerHTML = '${html}';
		document.body.insertBefore(svgDom, document.body.firstChild);
	}

	loadSvg();
}
		`;
    return { code, svgIcons };
}
