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
