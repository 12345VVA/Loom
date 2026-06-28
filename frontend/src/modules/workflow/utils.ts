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
