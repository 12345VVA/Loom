// @ts-ignore
import valueParser from "postcss-value-parser";
import { config } from "../config";
import type { Plugin } from "vite";
import { SAFE_CHAR_MAP } from "./config";
import {
	addScriptContent,
	getClassContent,
	getClassNames,
	getNodes,
	isTailwindClass,
} from "./utils";

/**
 * 转换类名中的特殊字符为安全字符
 */
export function toSafeClass(className: string): string {
	if (config.utsPlatform == "web") {
		return className;
	}

	if (className.includes(":host")) {
		return className;
	}

	// 如果是表达式,则不进行转换
	if (["!=", "!==", "?", ":", "="].includes(className)) {
		return className;
	}

	let safeClassName = className;

	// 移除转义字符
	if (safeClassName.includes("\\")) {
		safeClassName = safeClassName.replace(/\\/g, "");
	}

	// 处理暗黑模式
	if (safeClassName.includes(":is")) {
		if (safeClassName.includes(":is(.dark *)")) {
			safeClassName = safeClassName.replace(/:is\(.dark \*\)/g, "");
			if (safeClassName.startsWith(".dark:")) {
				const className = safeClassName.replace(/^\.dark:/, ".dark:");
				safeClassName = `${className}`;
			}
		}
	}

	// 替换特殊字符
	for (const [char, replacement] of Object.entries(SAFE_CHAR_MAP)) {
		const regex = new RegExp("\\" + char, "g");
		if (regex.test(safeClassName)) {
			safeClassName = safeClassName.replace(regex, replacement);
		}
	}

	return safeClassName;
}

/**
 * 转换 RGB 为 RGBA 格式
 */
function rgbToRgba(rgbValue: string): string {
	const match = rgbValue.match(/rgb\(([\d\s]+)\/\s*([\d.]+)\)/);
	if (!match) return rgbValue;

	const [, rgb, alpha] = match;
	const [r, g, b] = rgb.split(/\s+/);
	return `rgba(${r}, ${g}, ${b}, ${alpha})`;
}

function remToRpx(remValue: string): string {
	const { remUnit = 14, remPrecision = 6, rpxRatio = 2 } = config.tailwind!;
	const conversionFactor = remUnit * rpxRatio;

	const precision = (remValue.split(".")[1] || "").length;
	const rpxValue = (parseFloat(remValue) * conversionFactor)
		.toFixed(precision || remPrecision)
		.replace(/\.?0+$/, "");

	return `${rpxValue}rpx`;
}

/**
 * PostCSS 插件
 * 处理类名和单位转换
 */
function postcssPlugin(): Plugin {
	return {
		name: "vite-cool-uniappx-postcss",
		enforce: "pre",

		config() {
			return {
				css: {
					postcss: {
						plugins: [
							{
								postcssPlugin: "vite-cool-uniappx-class-mapping",
								prepare() {
									return {
										// 处理选择器规则
										Rule(rule: any) {
											if (
												[
													".button-hover",
													":deep(",
													"&::",
													"uni-",
													".uni-",
												].some((e) => rule.selector.includes(e))
											) {
												return;
											}

											// 转换选择器为安全的类名格式
											rule.selector = toSafeClass(rule.selector);
										},

										// 处理声明规则
										Declaration(decl: any) {
											const className = decl.parent.selector || "";

											if (!decl.parent._twValues) {
												decl.parent._twValues = {};
											}

											// 处理 Tailwind 自定义属性
											if (decl.prop.includes("--tw-")) {
												decl.parent._twValues[decl.prop] =
													decl.value.includes("rem")
														? remToRpx(decl.value)
														: decl.value;

												decl.remove();
												return;
											}

											// 转换 RGB 颜色为 RGBA 格式
											if (
												decl.value.includes("rgb(") &&
												decl.value.includes("/")
											) {
												decl.value = rgbToRgba(decl.value);
											}

											// 处理文本大小相关样式
											if (
												decl.value.includes("rpx") &&
												decl.prop == "color" &&
												className.includes("text-")
											) {
												decl.prop = "font-size";
											}

											// 删除不支持的属性
											if (["filter"].includes(decl.prop)) {
												decl.remove();
												return;
											}

											// 处理 flex-1
											if (decl.prop == "flex") {
												if (decl.value.startsWith("1")) {
													decl.value = "1";
												}
											}

											// 处理 vertical-align 属性
											if (decl.prop == "vertical-align") {
												decl.remove();
											}

											// 处理 visibility 属性
											if (decl.prop == "visibility") {
												decl.remove();
											}

											// 处理 sticky 属性
											if (className == ".sticky") {
												if (
													decl.prop == "position" ||
													decl.value == "sticky"
												) {
													decl.remove();
												}
											}

											// 解析声明值
											const parsed = valueParser(decl.value);
											let hasChanges = false;

											// 遍历并处理声明值中的节点
											parsed.walk((node: any) => {
												// 处理单位转换(rem -> rpx)
												if (node.type === "word") {
													const unit = valueParser.unit(node.value);

													if (typeof unit != "boolean") {
														if (unit?.unit === "rem") {
															node.value = remToRpx(unit.number);
															hasChanges = true;
														}
													}
												}

												// 处理 CSS 变量
												if (
													node.type === "function" &&
													node.value === "var"
												) {
													const twKey = node.nodes[0]?.value;

													// 替换 Tailwind 变量为实际值
													if (twKey?.startsWith("--tw-")) {
														if (decl.parent._twValues) {
															node.type = "word";
															node.value =
																decl.parent._twValues[twKey] ||
																"none";

															hasChanges = true;
														}
													}
												}
											});

											// 更新声明值
											if (hasChanges) {
												decl.value = parsed.toString();
											}

											// 移除 Tailwind 生成的无效 none 变换
											const nones = [
												"translate(none, none)",
												"rotate(none)",
												"skewX(none)",
												"skewY(none)",
												"scaleX(none)",
												"scaleY(none)",
											];

											if (decl.value) {
												nones.forEach((noneStr) => {
													decl.value = decl.value.replace(noneStr, "");

													if (!decl.value || !decl.value.trim()) {
														decl.value = "none";
													}
												});
											}
										},
									};
								},
							},
						],
					},
				},
			};
		},
	};
}

/**
 * uvue class 转换插件
 */
function transformPlugin(): Plugin {
	return {
		name: "vite-cool-uniappx-transform",
		enforce: "pre",

		async transform(code, id) {
			const { darkTextClass } = config.tailwind!;

			// 判断是否为 uvue 文件
			if (id.endsWith(".uvue") || id.includes(".uvue?type=page")) {
				// 避免影响到其他模块/插件
				if (id.includes("uni_modules/") && !id.includes("uni_modules/cool-")) {
					return null;
				}

				let modifiedCode = code;

				// 获取所有节点
				const nodes = getNodes(code);

				// 遍历处理每个节点
				nodes.forEach((node) => {
					if (node.startsWith("<!--")) {
						return;
					}

					let _node = node;

					// uniappx 插件模式
					if (!config.uniapp.isPlugin) {
						// 为 text 节点添加暗黑模式文本颜色
						if (!_node.includes(darkTextClass) && _node.startsWith("<text")) {
							let classIndex = _node.indexOf("class=");

							// 处理动态 class
							if (classIndex >= 0) {
								if (_node[classIndex - 1] == ":") {
									classIndex = _node.lastIndexOf("class=");
								}
							}

							// 添加暗黑模式类名
							if (classIndex >= 0) {
								_node =
									_node.substring(0, classIndex + 7) +
									`${darkTextClass} ` +
									_node.substring(classIndex + 7, _node.length);
							} else {
								_node =
									_node.substring(0, 5) +
									` class="${darkTextClass}" ` +
									_node.substring(5, _node.length);
							}
						}
					}

					// 获取所有类名
					const classNames = getClassNames(_node);

					// 转换 Tailwind 类名为安全类名
					classNames.forEach((name, index) => {
						if (isTailwindClass(name)) {
							const safeName = toSafeClass(name);
							_node = _node.replaceAll(name, safeName);
							classNames[index] = safeName;
						}
					});

					// 检查是否存在动态类名
					const hasDynamicClass = _node.includes(":class=");

					// 如果没有动态类名,添加空的动态类名绑定
					if (!hasDynamicClass) {
						// 优化写法，避免重复字符串拼接
						const insertIndex = _node.length - (_node.endsWith("/>") ? 2 : 1);

						_node =
							_node.slice(0, insertIndex) + ` :class="{}"` + _node.slice(insertIndex);
					}

					// 获取暗黑模式类名
					let darkClassNames = classNames.filter(
						(name) => name.startsWith("dark-colon-") || name.startsWith("dark:"),
					);

					// 插件模式，不支持 dark:
					if (config.uniapp.isPlugin) {
						darkClassNames = [];
					}

					// 生成暗黑模式类名的动态绑定
					const darkClassContent = darkClassNames
						.map((name) => {
							_node = _node.replaceAll(name, "");
							return `'${name}': __isDark`;
						})
						.join(",");

					// 获取所有 class 内容
					const classContents = getClassContent(_node);

					// 处理对象形式的动态类名
					const dynamicClassContent_1 = classContents.find(
						(content) => content.startsWith("{") && content.endsWith("}"),
					);

					if (dynamicClassContent_1) {
						const v =
							dynamicClassContent_1[0] +
							(darkClassContent ? `${darkClassContent},` : "") +
							dynamicClassContent_1.substring(1);

						_node = _node.replaceAll(dynamicClassContent_1, v);
					}

					// 处理数组形式的动态类名
					const dynamicClassContent_2 = classContents.find(
						(content) => content.startsWith("[") && content.endsWith("]"),
					);

					if (dynamicClassContent_2) {
						const v =
							dynamicClassContent_2[0] +
							`{${darkClassContent}},` +
							dynamicClassContent_2.substring(1);

						_node = _node.replaceAll(dynamicClassContent_2, v);
					}

					// 更新节点内容
					modifiedCode = modifiedCode.replace(node, _node);
				});

				// 如果代码有修改
				if (modifiedCode !== code) {
					// 添加暗黑模式依赖
					if (modifiedCode.includes("__isDark")) {
						if (!modifiedCode.includes("<script")) {
							modifiedCode += '<script lang="ts" setup></script>';
						}

						if (!config.uniapp.isPlugin) {
							modifiedCode = addScriptContent(
								modifiedCode,
								"\nimport { isDark as __isDark } from '@/cool';",
							);
						}
					}

					// 清理空的类名绑定
					modifiedCode = modifiedCode
						.replaceAll(':class="{}"', "")
						.replaceAll('class=""', "")
						.replaceAll('class=" "', "");

					return {
						code: modifiedCode,
						map: { mappings: "" },
					};
				}

				return null;
			} else {
				return null;
			}
		},
	};
}

/**
 * Tailwind 类名转换插件
 */
export function tailwindPlugin() {
	return [postcssPlugin(), transformPlugin()];
}
