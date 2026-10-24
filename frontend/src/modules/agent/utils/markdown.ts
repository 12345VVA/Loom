/**
 * 会话消息 markdown 安全渲染。
 *
 * assistant 回复按 GFM 渲染；DOMPurify 白名单剥离脚本/事件属性——消息内容来自
 * 模型输出（不可信输入），v-html 前必须过这道闸。user 气泡保持纯文本不经此通道。
 */
import DOMPurify from 'dompurify';
import { marked } from 'marked';

marked.setOptions({ gfm: true, breaks: true });

const ALLOWED_TAGS = [
	'p',
	'br',
	'hr',
	'h1',
	'h2',
	'h3',
	'h4',
	'h5',
	'h6',
	'strong',
	'em',
	'u',
	's',
	'code',
	'pre',
	'blockquote',
	'ul',
	'ol',
	'li',
	'a',
	'img',
	'table',
	'thead',
	'tbody',
	'tr',
	'th',
	'td',
	'span',
	'div',
	'sup',
	'sub'
];

const ALLOWED_ATTR = ['href', 'src', 'alt', 'title', 'class', 'target', 'rel'];

export function renderMarkdown(text?: string | null): string {
	if (!text) return '';
	try {
		const html = marked.parse(text, { async: false }) as string;
		return DOMPurify.sanitize(html, { ALLOWED_TAGS, ALLOWED_ATTR });
	} catch {
		// 渲染失败兜底为转义后的纯文本，不吞内容
		return DOMPurify.sanitize(text);
	}
}
