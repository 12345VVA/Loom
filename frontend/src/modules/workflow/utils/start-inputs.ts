/**
 * 开始节点输入变量声明解析。
 *
 * 兼容两种写法：
 *   - 旧：["query"]                          纯变量名，无默认值
 *   - 新：[{ name: "count", default: 10 }]   带默认值（后端 apply_start_input_defaults 消费）
 *   - v2：[{ name: "img", type: "image" }]   带类型声明（WFI-1b 多模态一期）
 *
 * 解析结果统一为对象，供画布配置面板、运行/试运行对话框、上游变量选择器共用。
 * type 缺省一律补 'string'（旧图零迁移兼容）；'string' 序列化时不落 type 键，
 * 保证旧图字节级不变。
 */

/** 输入变量类型（WFI-1b）：image 类型驱动试运行表单的上传控件与变量下拉过滤 */
export type StartInputVariableType = 'string' | 'number' | 'boolean' | 'image';

const VALID_TYPES: ReadonlySet<string> = new Set(['string', 'number', 'boolean', 'image']);

export interface StartInputVariable {
	/** 变量名 */
	name: string;
	/** 是否声明了默认值（用于区分「未声明」与「显式声明为 null」） */
	hasDefault: boolean;
	/** 默认值，仅 hasDefault 为 true 时有意义 */
	defaultValue: unknown;
	/** 变量类型，缺省 'string'（旧写法兼容） */
	type: StartInputVariableType;
}

function normalizeType(raw: unknown): StartInputVariableType {
	return typeof raw === 'string' && VALID_TYPES.has(raw) ? (raw as StartInputVariableType) : 'string';
}

export function parseStartInputVariables(raw: unknown): StartInputVariable[] {
	if (!Array.isArray(raw)) return [];
	const out: StartInputVariable[] = [];
	for (const item of raw) {
		if (typeof item === 'string') {
			const name = item.trim();
			if (name) out.push({ name, hasDefault: false, defaultValue: undefined, type: 'string' });
			continue;
		}
		if (item && typeof item === 'object') {
			const obj = item as Record<string, unknown>;
			const name = String(obj.name ?? '').trim();
			if (!name) continue;
			const hasDefault = Object.prototype.hasOwnProperty.call(obj, 'default');
			out.push({
				name,
				hasDefault,
				defaultValue: obj.default,
				type: normalizeType(obj.type)
			});
		}
	}
	return out;
}

/**
 * 由开始节点声明生成运行输入的初始表单值：
 * 声明了默认值的用默认值填充；未声明的按类型产初值
 * （image→''、number→0、boolean→false），交由表单/JSON 模式续填。
 */
export function buildStartInputsTemplate(raw: unknown): Record<string, unknown> {
	const tpl: Record<string, unknown> = {};
	for (const v of parseStartInputVariables(raw)) {
		if (v.hasDefault) {
			tpl[v.name] = v.defaultValue;
		} else if (v.type === 'number') {
			tpl[v.name] = 0;
		} else if (v.type === 'boolean') {
			tpl[v.name] = false;
		} else {
			tpl[v.name] = '';
		}
	}
	return tpl;
}
