import { firstUpperCase } from "../utils";

/**
 * 将模板字符串扁平化处理，转换为 Service 类型定义
 * @param template - 包含 Service 类型定义的模板字符串
 * @returns 处理后的 Service 类型定义字符串
 * @throws {Error} 当模板中找不到 Service 类型定义时抛出错误
 */
export function flatten(template: string): string {
	// 查找 Service 类型定义的起始位置
	const startIndex = template.indexOf("export type Service = {");

	// 保留 Service 类型定义前的内容
	let header = template.substring(0, startIndex);

	// 获取 Service 类型定义及其内容，去除换行和制表符
	const serviceTemplateContent = template.substring(startIndex).replace(/\n|\t/g, "");

	// 找到 Service 的内容部分
	const serviceStartIndex = serviceTemplateContent.indexOf("{") + 1;
	const serviceEndIndex = findClosingBrace(serviceTemplateContent, serviceStartIndex);
	const serviceInnerContent = serviceTemplateContent
		.substring(serviceStartIndex, serviceEndIndex)
		.trim();

	// 存储所有接口定义
	const allInterfaces = new Map<string, string>();

	// 处理 Service 内容，保持原有结构但替换嵌套对象为接口引用
	const serviceContent = buildCurrentLevelContent(serviceInnerContent);

	// 递归收集所有需要生成的接口
	flattenContent(serviceInnerContent, allInterfaces, []);

	// 生成所有接口定义
	let interfaces = "";
	allInterfaces.forEach((content, key) => {
		interfaces += `\nexport interface ${firstUpperCase(key)}Interface { ${content} }\n`;
	});

	return `${header}${interfaces}\nexport type Service = { ${serviceContent} }`;
}

/**
 * 查找匹配的右花括号位置
 * @param str - 要搜索的字符串
 * @param startIndex - 开始搜索的位置
 * @returns 匹配的右花括号位置
 * @throws {Error} 当找不到匹配的右花括号时抛出错误
 */
function findClosingBrace(str: string, startIndex: number): number {
	let braceCount = 1;
	let currentIndex = startIndex;

	while (currentIndex < str.length && braceCount > 0) {
		if (str[currentIndex] === "{") braceCount++;
		if (str[currentIndex] === "}") braceCount--;
		currentIndex++;
	}

	if (braceCount !== 0) {
		throw new Error("Unmatched braces in the template");
	}

	return currentIndex - 1;
}

/**
 * 递归收集所有需要生成的接口
 * @param content - 要处理的内容
 * @param allInterfaces - 存储所有接口定义的 Map
 * @param parentFields - 父级字段数组（暂未使用）
 */
function flattenContent(
	content: string,
	allInterfaces: Map<string, string>,
	parentFields: string[],
): void {
	const interfacePattern = /(\w+)\s*:\s*\{/g;
	let match: RegExpExecArray | null;

	while ((match = interfacePattern.exec(content)) !== null) {
		const key = match[1];
		const startIndex = match.index + match[0].length;
		const endIndex = findClosingBrace(content, startIndex);

		if (endIndex > startIndex) {
			const innerContent = content.substring(startIndex, endIndex).trim();

			// 构建当前接口的内容，将嵌套对象替换为接口引用
			const currentLevelContent = buildCurrentLevelContent(innerContent);
			allInterfaces.set(key, currentLevelContent);

			// 递归处理嵌套内容
			flattenContent(innerContent, allInterfaces, []);
		}
	}
}

/**
 * 构建当前级别的内容，将嵌套对象替换为接口引用
 * @param content - 内容字符串
 * @returns 处理后的内容
 */
function buildCurrentLevelContent(content: string): string {
	const interfacePattern = /(\w+)\s*:\s*\{/g;
	let result = content;
	let match: RegExpExecArray | null;

	// 重置正则表达式的 lastIndex
	interfacePattern.lastIndex = 0;

	while ((match = interfacePattern.exec(content)) !== null) {
		const key = match[1];
		const startIndex = match.index + match[0].length;
		const endIndex = findClosingBrace(content, startIndex);

		if (endIndex > startIndex) {
			const fullMatch = content.substring(match.index, endIndex + 1);
			const replacement = `${key}: ${firstUpperCase(key)}Interface;`;
			result = result.replace(fullMatch, replacement);
		}
	}

	// 清理多余的分号和空格
	result = result.replace(/;+/g, ";").replace(/\s+/g, " ").trim();

	return result;
}
