/**
 * 会话 markdown 安全渲染门禁：模型输出经 v-html 进 DOM，脚本注入与事件属性
 * 必须被剥离（utils/markdown.ts 的 DOMPurify 白名单）。
 */
import { describe, expect, it } from 'vitest';
import { renderMarkdown } from '/$/agent/utils/markdown';

describe('renderMarkdown 安全渲染', () => {
	it('基础 GFM 结构正常渲染', () => {
		const html = renderMarkdown('# 标题\n\n**粗体** 与 `code`\n\n- 列表项');
		expect(html).toContain('<h1>');
		expect(html).toContain('<strong>');
		expect(html).toContain('<code>');
		expect(html).toContain('<li>');
	});

	it('script 注入被剥离', () => {
		const html = renderMarkdown('前文<script>alert(1)</script>后文');
		expect(html).not.toContain('<script');
		expect(html).not.toContain('alert(1)');
		expect(html).toContain('前文');
	});

	it('事件属性被剥离', () => {
		const html = renderMarkdown('[点我](javascript:alert(1)) 和 <img src=x onerror="alert(1)">');
		expect(html).not.toContain('onerror');
		expect(html).not.toContain('javascript:');
	});

	it('iframe/object 危险标签被剥离', () => {
		const html = renderMarkdown('<iframe src="https://evil.example"></iframe><object></object>');
		expect(html).not.toContain('<iframe');
		expect(html).not.toContain('<object');
	});

	it('表格与代码块保留', () => {
		const html = renderMarkdown('| a | b |\n| - | - |\n| 1 | 2 |\n\n```js\nconst x = 1;\n```');
		expect(html).toContain('<table>');
		expect(html).toContain('const x = 1;');
	});

	it('空值与渲染失败兜底为空串/转义文本', () => {
		expect(renderMarkdown(null)).toBe('');
		expect(renderMarkdown('')).toBe('');
	});
});
