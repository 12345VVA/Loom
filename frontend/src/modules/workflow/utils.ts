import { ElMessage } from 'element-plus';

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
 * 复制文本到剪贴板，支持 HTTP 环境降级
 */
export async function copyToClipboard(
	text: string,
	successMsg = '复制成功',
	errorMsg = '复制失败'
) {
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
	} catch (err) {
		console.error('Clipboard copy failed:', err);
		ElMessage.error(errorMsg);
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
 * 节点配置必填字段缺失检测：返回缺失字段的中文标签列表（空数组 = 配置完整）。
 * 与 editor.vue 的 hasIncompleteNodes 判定同源；供配置面板做字段级内联提示。
 * 注：默认分支（start/end/loop_controller/batch_processor 等）无必填业务字段，返回 []。
 */
export function getMissingConfigFields(node: {
	type?: string;
	data?: { config?: Record<string, any> } | null;
}): string[] {
	const cfg = node?.data?.config || {};
	switch (node?.type) {
		case 'llm': {
			const miss: string[] = [];
			if (!cfg.modelProfileCode) miss.push('AI 模型');
			if (!cfg.promptTemplate) miss.push('提示词模板');
			return miss;
		}
		case 'condition':
			return !cfg.expression ? ['条件表达式'] : [];
		case 'switch': {
			const miss: string[] = [];
			if (!cfg.variable) miss.push('判断变量');
			if (!cfg.cases?.length) miss.push('分支配置');
			return miss;
		}
		case 'image_generator': {
			const miss: string[] = [];
			if (!cfg.modelProfileCode) miss.push('AI 模型');
			if (!cfg.promptTemplate) miss.push('提示词模板');
			return miss;
		}
		case 'tool_executor':
			return !cfg.toolCode ? ['工具'] : [];
		case 'human_input':
			return !cfg.message ? ['提示消息'] : [];
		case 'intent_classifier': {
			const miss: string[] = [];
			if (!cfg.modelProfileCode) miss.push('AI 模型');
			if (!cfg.intents?.length) miss.push('意图分支');
			return miss;
		}
		case 'variable_assignment':
			return !cfg.assignments?.length ? ['赋值规则'] : [];
		case 'variable_transform': {
			const miss: string[] = [];
			if (!cfg.input_variable) miss.push('输入变量');
			if (!cfg.transform_type) miss.push('转换类型');
			if (!cfg.output_variable) miss.push('输出变量');
			return miss;
		}
		default:
			return [];
	}
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
	nodeName?: string;
	nodeType?: string;
	inputData?: string;
	outputData?: string;
	status?: string;
	createTime?: string;
	isExpanded?: boolean;
}
