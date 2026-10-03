import { createDir, error, firstUpperCase, readFile, rootDir, toCamel } from "../utils";
import { join } from "path";
import axios from "axios";
import { compact, isArray, isEmpty, last, uniq, uniqBy, values } from "lodash";
import { createWriteStream } from "fs";
import prettier from "prettier";
import { config } from "../config";
import type { Eps } from "../../types";
import { flatten } from "../uniapp-x/flatten";
import { interfaceToType } from "../uniapp-x/utils";

// 全局 service 对象，用于存储服务结构
const service = {};
// eps 实体列表
let list: Eps.Entity[] = [];

/**
 * 获取 eps 请求地址
 * @returns {string} eps url
 */
function getEpsUrl(): string {
	let url = config.eps.api;

	if (!url) {
		url = config.type;
	}

	switch (url) {
		case "app":
		case "uniapp-x":
			url = "/app/base/comm/eps";
			break;
		case "admin":
			url = "/admin/base/open/eps";
			break;
	}

	return url;
}

/**
 * 获取 eps 路径
 * @param filename 文件名
 * @returns {string} 完整路径
 */
function getEpsPath(filename?: string): string {
	return join(
		config.type == "admin" ? config.eps.dist : rootDir(config.eps.dist),
		filename || "",
	);
}

/**
 * 获取对象方法名（排除 namespace、permission 字段）
 * @param v 对象
 * @returns {string[]} 方法名数组
 */
function getNames(v: any): string[] {
	return Object.keys(v).filter((e) => !["namespace", "permission"].includes(e));
}

/**
 * 获取字段类型
 */
function getType({ propertyName, type }: any) {
	for (const map of config.eps.mapping) {
		if (map.custom) {
			const resType = map.custom({ propertyName, type });
			if (resType) return resType;
		}
		if (map.test) {
			if (map.test.includes(type)) return map.type;
		}
	}
	return type;
}

/**
 * 格式化方法名，去除特殊字符
 */
function formatName(name: string) {
	return (name || "").replace(/[:,\s,\/,-]/g, "");
}

/**
 * 提取对象 schema 的字段体（"prop?: type;" 列表），非对象 schema 返回 null
 * @param schema OpenAPI schema（后端已解引用 $ref）
 * @param depth 递归深度
 */
function objectBody(schema: any, depth: number): string | null {
	if (!schema || typeof schema !== "object") {
		return null;
	}

	if (schema.anyOf || schema.oneOf || schema.enum) {
		return null;
	}

	if (schema.type !== "object" && !schema.properties) {
		return null;
	}

	const props = schema.properties || {};
	const keys = Object.keys(props);

	if (!keys.length) {
		return null;
	}

	const required: string[] = isArray(schema.required) ? schema.required : [];

	return keys
		.map((k) => {
			const p = props[k] || {};
			const key = checkName(k) ? k : `"${k}"`;
			return `/** ${p.description || k} */ ${key}${required.includes(k) ? "" : "?"}: ${schemaToTs(p, depth + 1)};`;
		})
		.join("\n");
}

/**
 * OpenAPI schema 转 TS 类型（防御式，异常一律兜底 any）
 * @param schema OpenAPI schema（后端已解引用 $ref）
 * @param depth 递归深度限制
 */
function schemaToTs(schema: any, depth = 0): string {
	try {
		if (!schema || typeof schema !== "object" || depth > 6) {
			return "any";
		}

		// 对象 → 内联类型
		const body = objectBody(schema, depth);
		if (body !== null) {
			return `{ ${body} }`;
		}

		// 联合类型 anyOf/oneOf
		const union = schema.anyOf || schema.oneOf;
		if (isArray(union)) {
			const parts = uniq(union.map((e: any) => schemaToTs(e, depth + 1)));
			return parts.length ? parts.join(" | ") : "any";
		}

		// 枚举字面量
		if (isArray(schema.enum) && schema.enum.length) {
			return schema.enum.map((e: any) => (typeof e === "string" ? `"${e}"` : String(e))).join(" | ");
		}

		// 数组
		if (schema.type === "array") {
			return `${schemaToTs(schema.items, depth + 1)}[]`;
		}

		// 标量（integer 已由后端归一为 number，此处兜底兼容）
		if (schema.type === "number" || schema.type === "integer") return "number";
		if (schema.type === "string") return "string";
		if (schema.type === "boolean") return "boolean";
		if (schema.type === "null") return "null";

		return "any";
	} catch {
		return "any";
	}
}

/**
 * 检查方法名是否合法（不包含特殊字符）
 */
function checkName(name: string) {
	return name && !["{", "}", ":"].some((e) => name.includes(e));
}

/**
 * 不支持 uniapp-x 平台显示
 */
function noUniappX(text: string, defaultText: string = "") {
	if (config.type == "uniapp-x") {
		return defaultText;
	} else {
		return text;
	}
}

/**
 * 查找字段
 * @param sources 字段 source 数组
 * @param item eps 实体
 * @returns {Eps.Column[]} 字段数组
 */
function findColumns(sources: string[], item: Eps.Entity): Eps.Column[] {
	const columns = [item.columns, item.pageColumns].flat().filter(Boolean);
	return (sources || [])
		.map((e) => columns.find((c) => c.source == e))
		.filter(Boolean) as Eps.Column[];
}

/**
 * 使用 prettier 格式化 TypeScript 代码
 * @param text 代码文本
 * @returns {Promise<string|null>} 格式化后的代码
 */
async function formatCode(text: string): Promise<string | null> {
	return prettier
		.format(text, {
			parser: "typescript",
			useTabs: true,
			tabWidth: 4,
			endOfLine: "lf",
			semi: true,
			singleQuote: false,
			printWidth: 100,
			trailingComma: "none",
		})
		.catch((err) => {
			console.log(err);
			error(`[cool-eps] File format error, please try again`);
			return null;
		});
}

/**
 * 获取 eps 数据（本地优先，远程兜底）
 */
async function getData() {
	// 读取本地 eps.json
	list = readFile(getEpsPath("eps.json"), true) || [];

	// 拼接请求地址
	const url = config.reqUrl + getEpsUrl();

	// 请求远程 eps 数据
	await axios
		.get(url, {
			timeout: 5000,
		})
		.then((res) => {
			const { code, data, message } = res.data;
			if (code === 1000) {
				if (!isEmpty(data) && data) {
					list = values(data).flat();
				}
			} else {
				error(`[cool-eps] ${message || "Failed to fetch data"}`);
			}
		})
		.catch(() => {
			error(`[cool-eps] API service is not running → ${url}`);
		});

	// 初始化处理，补全缺省字段
	list.forEach((e) => {
		if (!e.namespace) e.namespace = "";
		if (!e.api) e.api = [];
		if (!e.columns) e.columns = [];
		if (!e.search) {
			e.search = {
				fieldEq: findColumns(e.pageQueryOp?.fieldEq, e),
				fieldLike: findColumns(e.pageQueryOp?.fieldLike, e),
				keyWordLikeFields: findColumns(e.pageQueryOp?.keyWordLikeFields, e),
			};
		}
	});

	if (config.type == "uniapp-x" || config.type == "app") {
		list = list.filter((e) => e.prefix.startsWith("/app") || e.prefix.startsWith("/admin"));
	}
}

/**
 * 创建 eps.json 文件
 * @returns {boolean} 是否有更新
 */
function createJson(): boolean {
	let data: any[] = [];

	if (config.type != "uniapp-x") {
		data = list.map((e) => {
			return {
				prefix: e.prefix,
				name: e.name || "",
				api: e.api.map((apiItem) => ({
					name: apiItem.name,
					method: apiItem.method,
					path: apiItem.path,
					// 持久化 dts/columns，后端不可达时重生成不降级
					dts: apiItem.dts,
				})),
				search: e.search,
				columns: e.columns,
				pageColumns: e.pageColumns,
			};
		});
	} else {
		data = list;
	}

	const content = JSON.stringify(data);
	const local_content = readFile(getEpsPath("eps.json"));

	// 判断是否需要更新
	const isUpdate = content != local_content;

	if (isUpdate) {
		createWriteStream(getEpsPath("eps.json"), {
			flags: "w",
		}).write(content);
	}

	return isUpdate;
}

/**
 * 创建 eps 类型描述文件（d.ts/ts）
 * @param param0 list: eps实体列表, service: service对象
 */
async function createDescribe({ list, service }: { list: Eps.Entity[]; service: any }) {
	/**
	 * 创建 Entity 接口定义
	 */
	function createEntity() {
		const ignore: string[] = [];
		let t0 = "";

		for (const item of list) {
			if (!checkName(item.name)) continue;

			let t = `interface ${formatName(item.name)} {`;

			// 合并 columns 和 pageColumns，去重
			const columns: Eps.Column[] = uniqBy(
				compact([...(item.columns || []), ...(item.pageColumns || [])]),
				"source",
			);

			for (const col of columns || []) {
				t += `
					/**
					 * ${col.comment}
					 */
					${col.propertyName}?: ${getType({
						propertyName: col.propertyName,
						type: col.type,
					})};
				`;
			}

			t += `
				/**
				 * 任意键值
				 */
				[key: string]: any;
			}
			`;

			if (!ignore.includes(item.name)) {
				ignore.push(item.name);
				t0 += t + "\n\n";
			}
		}

		return t0;
	}

	/**
	 * 创建 Controller 接口定义
	 */
	async function createController() {
		let controller = "";
		let chain = "";
		let pageResponse = "";

		// 已提升的具名 Response 接口（去重）
		const namedResponses = new Set<string>();

		/**
		 * 非标准 CRUD 路径的返回类型：优先从 OpenAPI responses 推导
		 * （响应经拦截器解包，此处描述的是解包后的 data 载荷）
		 * @param name 控制器接口名
		 * @param action 方法名（驼峰）
		 * @param dts OpenAPI 元数据
		 */
		function actionResponse(name: string, action: string, dts: any): string {
			const schema = dts?.responses?.["200"]?.content?.["application/json"]?.schema;

			if (!schema || typeof schema !== "object") {
				return "any";
			}

			// 顶层对象提升为具名接口（与 PageResponse 并排声明），标量/数组/联合内联
			const body = objectBody(schema, 1);

			if (body !== null) {
				const tsName = `${name}${firstUpperCase(action)}Response`;

				if (!namedResponses.has(tsName)) {
					namedResponses.add(tsName);
					pageResponse += `\ninterface ${tsName} {\n${body}\n}\n`;
				}

				return tsName;
			}

			return schemaToTs(schema);
		}

		/**
		 * 递归处理 service 树，生成接口定义
		 * @param d 当前节点
		 * @param k 前缀
		 */
		function deep(d: any, k?: string) {
			if (!k) k = "";

			for (const i in d) {
				const name = k + toCamel(firstUpperCase(formatName(i)));

				// 检查方法名
				if (!checkName(name)) continue;

				if (d[i].namespace) {
					// 查找配置
					const item = list.find((e) => (e.prefix || "") === `/${d[i].namespace}`);

					if (item) {
						//
						let t = `interface ${name} {`;

						// 插入方法
						if (item.api) {
							// 权限列表
							const permission: string[] = [];

							item.api.forEach((a) => {
								// 方法名
								const n = toCamel(formatName(a.name || last(a.path.split("/"))!));

								// 检查方法名
								if (!checkName(n)) return;

								if (n) {
									// 参数类型
									let q: string[] = [];

									// 参数列表
									const { parameters = [] } = a.dts || {};

									// POST/PUT 有请求体：query 参数冒充 body 会过度约束调用侧，参数侧保持 any
									const hasBody =
										["post", "put", "patch"].includes(String(a.method || "").toLowerCase()) ||
										a.dts?.requestBody;

									if (hasBody) {
										q = ["any"];
									} else {
										parameters.forEach((p) => {
											if (p.description) {
												q.push(`\n/** ${p.description}  */\n`);
											}

											// 检查参数名
											if (!checkName(p.name)) {
												return false;
											}

											const a = `${p.name}${p.required ? "" : "?"}`;
											const b = `${p.schema?.type || "string"}`;

											q.push(`${a}: ${b};`);
										});

										if (isEmpty(q)) {
											q = ["any"];
										} else {
											q.unshift("{");
											q.push("}");
										}
									}

									// 全部参数可选时 data 可省略，保持无参调用兼容
									const dataOptional =
										q.length == 1 || (parameters.length > 0 && parameters.every((p) => !p.required));

									// 返回类型
									let res = "";

									// 实体名
									const en = item.name || "any";

									switch (a.path) {
										case "/page":
											res = `${name}PageResponse`;

											pageResponse += `
												interface ${name}PageResponse {
													pagination: PagePagination;
													list: ${en}[];
												}
											`;

											break;
										case "/list":
											res = `${en} []`;
											break;
										case "/info":
											res = en;
											break;
										default:
											res = actionResponse(name, n, a.dts);
											break;
									}

									// 方法描述
									if (config.type == "uniapp-x") {
										t += `
											/**
											 * ${a.summary || n}
											 */
											${n}(data${dataOptional ? "?" : ""}: ${q.join("")}): Promise<any>;
										`;
									} else {
										t += `
											/**
											 * ${a.summary || n}
											 */
											${n}(data${dataOptional ? "?" : ""}: ${q.join("")}): Promise<${res}>;
										`;
									}

									if (!permission.includes(n)) {
										permission.push(n);
									}
								}
							});

							// 权限标识
							t += noUniappX(`
								/**
								 * 权限标识
								 */
								permission: { ${permission.map((e) => `${e}: string;`).join("\n")} };
							`);

							// 权限状态
							t += noUniappX(`
								/**
								 * 权限状态
								 */
								_permission: { ${permission.map((e) => `${e}: boolean;`).join("\n")} };
							`);

							// 请求
							t += noUniappX(`
								request: Request;
							`);
						}

						t += "}\n\n";

						controller += t;
						chain += `${formatName(i)}: ${name};`;
					}
				} else {
					chain += `${formatName(i)}: {`;
					deep(d[i], name);
					chain += "};";
				}
			}
		}

		// 遍历 service 树
		deep(service);

		return `
			type json = any;

			${await createDict()}

			interface PagePagination {
				size: number;
				page: number;
				total: number;
				[key: string]: any;
			};

			interface PageResponse<T> {
				pagination: PagePagination;
				list: T[];
				[key: string]: any;
			};

			${pageResponse}

			${controller}

			${noUniappX(`interface RequestOptions {
				url: string;
				method?: 'OPTIONS' | 'GET' | 'HEAD' | 'POST' | 'PUT' | 'DELETE' | 'TRACE' | 'CONNECT';
				data?: any;
				params?: any;
				headers?: any;
				timeout?: number;
				[key: string]: any;
			}`)}

			${noUniappX("type Request = (options: RequestOptions) => Promise<any>;")}

			type Service = {
				${noUniappX("request: Request;")}

				${chain}
			}
		`;
	}

	// 组装文件内容
	let text = `
		${createEntity()}
		${await createController()}
	`;

	// 文件名
	let name = "eps.d.ts";

	if (config.type == "uniapp-x") {
		name = "eps.ts";
		text = text
			.replaceAll("interface ", "export interface ")
			.replaceAll("type ", "export type ")
			.replaceAll("[key: string]: any;", "");

		text = flatten(text);
		text = interfaceToType(text);
	} else {
		text = `
			declare namespace Eps {
				${text}
			}
		`;
	}

	// 格式化文本内容
	const content = await formatCode(text);

	const local_content = readFile(getEpsPath(name));

	// 是否需要更新
	if (content && content != local_content && list.length > 0) {
		// 创建 eps 描述文件
		createWriteStream(getEpsPath(name), {
			flags: "w",
		}).write(content);
	}
}

/**
 * 构建 service 对象树
 */
function createService() {
	// 路径第一层作为 id 标识
	const id = getEpsUrl().split("/")[1];

	list.forEach((e) => {
		// 请求地址
		const path = e.prefix[0] == "/" ? e.prefix.substring(1, e.prefix.length) : e.prefix;

		// 分隔路径，去除 id，转驼峰
		const arr = path.replace(id, "").split("/").filter(Boolean).map(toCamel);

		/**
		 * 递归构建 service 树
		 * @param d 当前节点
		 * @param i 当前索引
		 */
		function deep(d: any, i: number) {
			const k = arr[i];

			if (k) {
				// 是否最后一个
				if (arr[i + 1]) {
					if (!d[k]) {
						d[k] = {};
					}
					deep(d[k], i + 1);
				} else {
					// 不存在则创建
					if (!d[k]) {
						d[k] = {
							permission: {},
						};
					}

					if (!d[k].namespace) {
						d[k].namespace = path;
					}

					// 创建权限
					if (d[k].namespace) {
						getNames(d[k]).forEach((i) => {
							d[k].permission[i] =
								`${d[k].namespace.replace(`${id}/`, "")}/${i}`.replace(/\//g, ":");
						});
					}

					// 创建搜索
					d[k].search = e.search;

					// 创建方法
					e.api.forEach((a) => {
						// 方法名
						const n = a.path.replace("/", "");
						if (n && !/[-:]/g.test(n)) {
							d[k][n] = a;
						}
					});
				}
			}
		}

		deep(service, 0);
	});
}

/**
 * 创建 service 代码
 * @returns {string} service 代码
 */
function createServiceCode(): { content: string; types: string[] } {
	const types: string[] = [];

	let chain = "";

	/**
	 * 递归处理 service 树，生成接口代码
	 * @param d 当前节点
	 * @param k 前缀
	 */
	function deep(d: any, k?: string) {
		if (!k) k = "";

		for (const i in d) {
			if (["swagger"].includes(i)) {
				continue;
			}

			const name = k + toCamel(firstUpperCase(formatName(i)));

			// 检查方法名
			if (!checkName(name)) continue;

			if (d[i].namespace) {
				// 查找配置
				const item = list.find((e) => (e.prefix || "") === `/${d[i].namespace}`);

				if (item) {
					//
					let t = `{`;

					// 插入方法
					if (item.api) {
						item.api.forEach((a) => {
							// 方法名
							const n = toCamel(formatName(a.name || last(a.path.split("/"))!));

							// 检查方法名
							if (!checkName(n)) return;

							if (n) {
								// 参数类型
								let q: string[] = [];

								// 参数列表
								const { parameters = [] } = a.dts || {};

								parameters.forEach((p) => {
									if (p.description) {
										q.push(`\n/** ${p.description}  */\n`);
									}

									// 检查参数名
									if (!checkName(p.name)) {
										return false;
									}

									const a = `${p.name}${p.required ? "" : "?"}`;
									const b = `${p.schema.type || "string"}`;

									q.push(`${a}: ${b}, `);
								});

								if (isEmpty(q)) {
									q = ["any"];
								} else {
									q.unshift("{");
									q.push("}");
								}

								if (item.name) {
									types.push(item.name);
								}

								// 方法描述
								t += `
									/**
									 * ${a.summary || n}
									 */
									${n}(data?: any): Promise<any> {
										return request({
											url: "/${d[i].namespace}${a.path}",
											method: "${(a.method || "get").toLocaleUpperCase()}",
											data,
										});
									},
								`;
							}
						});
					}

					t += `} as ${name}\n`;

					types.push(name);

					chain += `${formatName(i)}: ${t},\n`;
				}
			} else {
				chain += `${formatName(i)}: {`;
				deep(d[i], name);
				chain += `} as ${firstUpperCase(i)}Interface,`;

				types.push(`${firstUpperCase(i)}Interface`);
			}
		}
	}

	// 遍历 service 树
	deep(service);

	return {
		content: `{ ${chain} }`,
		types,
	};
}

/**
 * 获取字典类型定义
 * @returns {Promise<string>} 字典类型 type 定义
 */
async function createDict(): Promise<string> {
	let p = "";

	switch (config.type) {
		case "app":
		case "uniapp-x":
			p = "/app";
			break;
		case "admin":
			p = "/admin";
			break;
	}

	const url = config.reqUrl + p + "/dict/info/types";

	const text = await axios
		.get(url)
		.then((res) => {
			const { code, data } = res.data as { code: number; data: any[] };

			if (code === 1000) {
				let v = "string";
				if (!isEmpty(data)) {
					v = data.map((e) => `"${e.key}"`).join(" | ");
				}
				return `type DictKey = ${v}`;
			}
		})
		.catch(() => {
			error(`[cool-eps] Error：${url}`);
		});

	// 后端不可达时兜底，避免 DictKey 引用悬空
	return text || "type DictKey = string;";
}

/**
 * 主入口：创建 eps 相关文件和 service
 */
export async function createEps() {
	if (config.eps.enable) {
		// 获取 eps 数据
		await getData();

		// 构建 service 对象
		createService();

		const serviceCode = createServiceCode();

		// 创建 eps 目录
		createDir(getEpsPath(), true);

		// 创建 eps.json 文件
		const isUpdate = createJson();

		// 创建类型描述文件
		createDescribe({ service, list });

		return {
			service,
			serviceCode,
			list,
			isUpdate,
		};
	} else {
		return {
			service: {},
			list: [],
		};
	}
}
