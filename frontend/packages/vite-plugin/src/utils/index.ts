import fs from "fs";
import { join } from "path";
import { config } from "../config";
import prettier from "prettier";

// 根目录
export function rootDir(path: string) {
	switch (config.type) {
		case "app":
		case "uniapp-x":
			return join(process.env.UNI_INPUT_DIR!, path);

		default:
			return join(process.cwd(), path);
	}
}

// 首字母大写
export function firstUpperCase(value: string): string {
	return value.replace(/\b(\w)(\w*)/g, function ($0, $1, $2) {
		return $1.toUpperCase() + $2;
	});
}

// 横杠转驼峰
export function toCamel(str: string): string {
	return str.replace(/([^-])(?:-+([^-]))/g, function ($0, $1, $2) {
		return $1 + $2.toUpperCase();
	});
}

// 创建目录
export function createDir(path: string, recursive?: boolean) {
	try {
		if (!fs.existsSync(path)) fs.mkdirSync(path, { recursive });
	} catch (err) {}
}

// 读取文件
export function readFile(path: string, json?: boolean) {
	try {
		const content = fs.readFileSync(path, "utf8");
		return json ? JSON.parse(removeJsonComments(content)) : content;
	} catch (err) {}

	return "";
}

// 安全地移除JSON中的注释
function removeJsonComments(content: string): string {
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
		} else if (inString && char === stringChar && !escaped) {
			inString = false;
			stringChar = "";
			result += char;
		} else if (inString) {
			// 在字符串内，直接添加字符
			result += char;
			escaped = char === "\\" && !escaped;
		} else {
			// 不在字符串内，检查注释
			if (char === "/" && nextChar === "/") {
				// 单行注释，跳过到行尾
				while (i < content.length && content[i] !== "\n") {
					i++;
				}
				if (i < content.length) {
					result += content[i]; // 保留换行符
				}
			} else if (char === "/" && nextChar === "*") {
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
			} else {
				result += char;
				escaped = false;
			}
		}

		i++;
	}

	return result;
}

// 写入文件
export function writeFile(path: string, data: any) {
	try {
		return fs.writeFileSync(path, data);
	} catch (err) {}

	return "";
}

// 解析body
export function parseJson(req: any): Promise<any> {
	return new Promise((resolve) => {
		let d = "";
		req.on("data", function (chunk: any) {
			d += chunk;
		});
		req.on("end", function () {
			try {
				resolve(JSON.parse(d));
			} catch {
				resolve({});
			}
		});
	});
}

// 格式化内容
export function formatContent(content: string, options?: prettier.Options) {
	return prettier.format(content, {
		parser: "typescript",
		useTabs: true,
		tabWidth: 4,
		endOfLine: "lf",
		semi: true,
		...options,
	});
}

export function error(message: string) {
	console.log("\x1B[31m%s\x1B[0m", message);
}

export function success(message: string) {
	console.log("\x1B[32m%s\x1B[0m", message);
}

/**
 * 比较两个版本号
 * @param version1 版本号1 (如: "1.2.3")
 * @param version2 版本号2 (如: "1.2.4")
 * @returns 1: version1 > version2, 0: 相等, -1: version1 < version2
 */
export function compareVersion(version1: string, version2: string): number {
	const v1Parts = version1.split(".").map(Number);
	const v2Parts = version2.split(".").map(Number);

	const maxLength = Math.max(v1Parts.length, v2Parts.length);

	for (let i = 0; i < maxLength; i++) {
		const v1Part = v1Parts[i] || 0;
		const v2Part = v2Parts[i] || 0;

		if (v1Part > v2Part) return 1;
		if (v1Part < v2Part) return -1;
	}

	return 0;
}
