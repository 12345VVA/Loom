// workflow_annotation 模块的纯格式化/解析工具函数。
// 从 views/annotation-drawer.vue 中抽离，便于单元测试与复用。
// 注意：本文件不依赖 vue-i18n / element-plus 运行时，仅做纯数据映射与 JSON 解析。

/**
 * 将后端 JSON 字符串快照（inputData / actualOutput 等）美化展示。
 * - 空值（null/undefined/''）→ ''
 * - 合法 JSON 字符串 → 解析后 2 空格缩进序列化
 * - 对象 → 直接 2 空格缩进序列化
 * - 解析失败 → 回退 String(s)
 * - 解析后是字符串（如已是裸字符串的 JSON）→ 直接返回该字符串
 */
export function pretty(s: any): string {
	if (s === null || s === undefined || s === '') return '';
	try {
		const obj = typeof s === 'string' ? JSON.parse(s) : s;
		return typeof obj === 'string' ? obj : JSON.stringify(obj, null, 2);
	} catch {
		return String(s);
	}
}

/**
 * 解析 evaluator_detail 字段：兼容 string（JSON）与 object 两种存储形式。
 * 入参为空返回 null；解析失败返回 null（不抛错，供抽屉兜底渲染）。
 */
export function parseJudgeDetail(s: any): any {
	if (!s) return null;
	try {
		return typeof s === 'string' ? JSON.parse(s) : s;
	} catch {
		return null;
	}
}
