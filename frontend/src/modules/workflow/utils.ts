import { ElMessage } from 'element-plus';
import { NODE_MANIFEST } from './generated/node-manifest';

/**
 * 格式化 JSON 字符串为美观的缩进形式
 */
export function formatJson(val?: string): string {
	if (!val) return '{}';
	try {
		const parsed = JSON.parse(val);
		return JSON.stringify(parsed, null, 2);
	} catch (e) {
		return val;
	}
}

/**
 * 格式化工作流版本号：整数序号 → V0.0.x（如 1 → V0.0.1）
 * 后端 version_no 仍是递增整数，前端统一展示为语义化样式。
 */
export function formatVersionNo(n: number | null | undefined): string {
	if (n === null || n === undefined) return '-';
	return `V0.0.${n}`;
}

/**
 * 复制文本到剪贴板，支持 HTTP 环境降级。
 * 成功/失败提示由本函数统一弹出（消息文案必须由调用方传入 t() 结果，
 * 避免硬编码中文绕过 i18n）；返回是否成功，调用方如需附加逻辑据此分支。
 */
export async function copyToClipboard(text: string, successMsg: string, errorMsg: string) {
	try {
		if (navigator.clipboard && window.isSecureContext) {
			await navigator.clipboard.writeText(text);
		} else {
			// 降级方案
			const textarea = document.createElement('textarea');
			textarea.value = text;
			// 避免滚动
			textarea.style.position = 'fixed';
			textarea.style.opacity = '0';
			document.body.appendChild(textarea);
			textarea.select();
			document.execCommand('copy');
			document.body.removeChild(textarea);
		}
		ElMessage.success(successMsg);
		return true;
	} catch (err) {
		console.error('Clipboard copy failed:', err);
		ElMessage.error(errorMsg);
		return false;
	}
}

/**
 * 生成短随机 id（base36 子串必含字母，不会与纯数字下标混淆）
 * 用于 switch/intent 分支端口的稳定 handle id：删除中间项时其余边不再错位
 */
export function genId(prefix = ''): string {
	let s = Math.random().toString(36).substring(2, 10);
	// 保证含字母：避免生成纯数字 id 与旧下标格式（case_<纯数字>）混淆。
	// 加载迁移正则 /^case_\d+$/ 依赖“新 id 必含字母”这一不变量区分新旧格式。
	if (/^\d+$/.test(s)) s = 'z' + s;
	return prefix + s;
}

/**
 * 读取节点输出变量名（兼容两种历史字段名）。
 *
 * variable_transform 历史上使用下划线字段 output_variable，三期B7（WF-P2-9）起
 * 权威统一驼峰（写入侧见 node-default-configs.ts 的 outputVarKey），此处 snake 仅
 * 存量图兜底。任何只读单侧字段的地方都会漏读另一侧，导致其在下游变量选择器不可见、
 * 重名去重失效。
 */
export function resolveOutputVar(cfg: Record<string, any> | undefined | null): string {
	if (!cfg) return '';
	return String(cfg.outputVariable || cfg.output_variable || '').trim();
}

/**
 * 校验节点 inputs 变量名合法性：非空、符合标识符规则、不重名。
 * 返回首个非法项 { label, error }；全部合法返回 null。供保存/测试前阻断使用。
 */
const NODE_INPUT_NAME_REGEX = /^[a-zA-Z_][a-zA-Z0-9_]*$/;

export function findInvalidNodeInput(nodes: any[]): { label: string; error: string } | null {
	for (const node of nodes) {
		if ('source' in node) continue; // 跳过边
		const inputs = node?.data?.config?.inputs;
		if (!Array.isArray(inputs) || inputs.length === 0) continue;
		const label = node.label || node.id || '节点';
		const seen = new Set<string>();
		for (const inp of inputs) {
			const name = (inp?.name || '').trim();
			if (!name) {
				return { label, error: `节点「${label}」存在未命名的输入变量` };
			}
			if (!NODE_INPUT_NAME_REGEX.test(name)) {
				return { label, error: `节点「${label}」输入变量「${name}」仅支持英文字母、数字和下划线` };
			}
			if (seen.has(name)) {
				return { label, error: `节点「${label}」输入变量「${name}」重复` };
			}
			seen.add(name);
		}
	}
	return null;
}

/**
 * camelCase → snake_case（存量图兜底取值用，与后端 get_config_value 双风格对应）
 */
function _camelToSnake(key: string): string {
	return key.replace(/([A-Z])/g, '_$1').toLowerCase();
}

/**
 * 必填判定（对齐后端 node_schema._is_blank）：null/undefined/空白字符串/
 * 空数组/空对象 视为缺失。
 */
function _isBlank(val: unknown): boolean {
	if (val === null || val === undefined) return true;
	if (typeof val === 'string') return !val.trim();
	if (Array.isArray(val) || typeof val === 'object') return Object.keys(val as object).length === 0;
	return false;
}

/**
 * 节点配置必填字段缺失检测：返回缺失字段的中文标签列表（空数组 = 配置完整）。
 * 与 editor.vue 的 hasIncompleteNodes 判定同源；供配置面板做字段级内联提示。
 *
 * F3（UI/UX 审查 2026-10-10）起必填口径单一来源化：从 node-manifest 的
 * configFields（后端 NODE_CONFIG_SCHEMA 经 dump_node_manifest.py 导出）派生，
 * 消除前端手工 switch / 面板星号 / 后端 schema 三处漂移。snake_case 仅存量图
 * 兜底读取（同 resolveOutputVar 口径）。intent_classifier 无静态必填
 * （modelProfileCode 是「intents 非空才必填」的条件语义，由后端 step6 权威校验）。
 */
export function getMissingConfigFields(node: {
	type?: string;
	data?: { config?: Record<string, any> } | null;
}): string[] {
	const fields = NODE_MANIFEST.find(n => n.type === node?.type)?.configFields ?? [];
	if (!fields.length) return [];
	const cfg = node?.data?.config || {};
	const miss: string[] = [];
	for (const field of fields) {
		if (!field.required) continue;
		const val = cfg[field.key] ?? cfg[_camelToSnake(field.key)];
		if (_isBlank(val)) miss.push(field.label);
	}
	return miss;
}

/**
 * 节点配置是否不完整（存在缺失的必填字段）。基于 getMissingConfigFields，
 * 供 hasIncompleteNodes 等仅需布尔判定的场景使用。
 */
export function isRequiredConfigMissing(node: {
	type?: string;
	data?: { config?: Record<string, any> } | null;
}): boolean {
	return getMissingConfigFields(node).length > 0;
}

/**
 * 工作流执行日志项（节点级输入/输出快照）。
 * editor 测试运行抽屉与 instance 步骤日志抽屉共用，供 <LogDrawer> 组件统一渲染。
 */
export interface WorkflowLogItem {
	id?: number;
	instanceId?: number;
	nodeId?: string;
	nodeName?: string;
	nodeType?: string;
	inputData?: string;
	outputData?: string;
	latencyMs?: number;
	status?: string;
	/** 节点失败原因（status=error 时后端写入），抽屉红色错误区块展示 */
	errorMessage?: string;
	createTime?: string;
	isExpanded?: boolean;
}
