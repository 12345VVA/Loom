import { marked } from 'marked';
import DOMPurify from 'dompurify';

// 初始化并锁定 Marked 基础配置
marked.setOptions({
	gfm: true,
	breaks: true
});

/**
 * 将 Markdown 字符串解析为经过 DOMPurify 安全净化的 HTML
 */
export function renderMarkdown(content: string): string {
	if (!content) return '';
	try {
		const raw = marked.parse(content, { async: false }) as string;
		return DOMPurify.sanitize(raw);
	} catch (e) {
		return content;
	}
}
