/**
 * 开始节点输入变量声明解析。
 *
 * 兼容两种写法：
 *   - 旧：["query"]                          纯变量名，无默认值
 *   - 新：[{ name: "count", default: 10 }]   带默认值（后端 apply_start_input_defaults 消费）
 *
 * 解析结果统一为对象，供画布配置面板、运行/试运行对话框、上游变量选择器共用。
 */

export interface StartInputVariable {
	/** 变量名 */
	name: string;
	/** 是否声明了默认值（用于区分「未声明」与「显式声明为 null」） */
	hasDefault: boolean;
	/** 默认值，仅 hasDefault 为 true 时有意义 */
	defaultValue: unknown;
}

export function parseStartInputVariables(raw: unknown): StartInputVariable[] {
	if (!Array.isArray(raw)) return [];
	const out: StartInputVariable[] = [];
	for (const item of raw) {
		if (typeof item === 'string') {
			const name = item.trim();
			if (name) out.push({ name, hasDefault: false, defaultValue: undefined });
			continue;
		}
		if (item && typeof item === 'object') {
			const obj = item as Record<string, unknown>;
			const name = String(obj.name ?? '').trim();
			if (!name) continue;
			const hasDefault = Object.prototype.hasOwnProperty.call(obj, 'default');
			out.push({ name, hasDefault, defaultValue: obj.default });
		}
	}
	return out;
}

/**
 * 由开始节点声明生成运行输入的初始 JSON 模板：
 * 声明了默认值的用默认值填充，其余留空串由用户填写。
 */
export function buildStartInputsTemplate(raw: unknown): Record<string, unknown> {
	const tpl: Record<string, unknown> = {};
	for (const v of parseStartInputVariables(raw)) {
		tpl[v.name] = v.hasDefault ? v.defaultValue : '';
	}
	return tpl;
}
