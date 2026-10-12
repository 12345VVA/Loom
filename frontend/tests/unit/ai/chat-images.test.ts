import { describe, expect, it } from 'vitest';
import {
	CHAT_IMAGE_MAX_COUNT,
	buildMessageContent,
	readFileAsDataUri,
	supportsVision,
	validateImageFile
} from '/$/ai/utils/chat-images';

function makeImageFile(type = 'image/png', sizeMb = 0.01) {
	return new File([new ArrayBuffer(sizeMb * 1024 * 1024)], 'a.png', { type });
}

describe('ai/utils/chat-images', () => {
	describe('validateImageFile', () => {
		it('白名单类型通过', () => {
			for (const type of ['image/png', 'image/jpeg', 'image/webp', 'image/gif']) {
				expect(validateImageFile(makeImageFile(type))).toBeNull();
			}
		});

		it('SVG 拒绝（可内嵌脚本，与后端白名单口径一致）', () => {
			expect(validateImageFile(makeImageFile('image/svg+xml'))).toContain('不支持的图片类型');
		});

		it('非图片类型拒绝', () => {
			expect(validateImageFile(makeImageFile('text/plain'))).toContain('不支持的图片类型');
		});

		it('超过 5MB 拒绝', () => {
			expect(validateImageFile(makeImageFile('image/png', 6))).toContain('5MB');
		});
	});

	describe('buildMessageContent', () => {
		it('无图时保持 str（纯文本请求格式零变化）', () => {
			expect(buildMessageContent('你好')).toBe('你好');
			expect(buildMessageContent('你好', [])).toBe('你好');
			expect(buildMessageContent('你好', undefined)).toBe('你好');
		});

		it('有图时组装 IR parts：text 在前，image_url 在后', () => {
			const parts = buildMessageContent('看这张图', ['data:image/png;base64,AAA']);
			expect(parts).toEqual([
				{ type: 'text', text: '看这张图' },
				{ type: 'image_url', image_url: { url: 'data:image/png;base64,AAA' } }
			]);
		});

		it('多图顺序保持', () => {
			const parts: any[] = buildMessageContent('t', ['data:a', 'data:b', 'data:c']);
			expect(parts.filter(p => p.type === 'image_url')).toHaveLength(3);
			expect(parts[1].image_url.url).toBe('data:a');
			expect(parts[3].image_url.url).toBe('data:c');
		});

		it('空文本省略 text part（纯图消息）', () => {
			const parts = buildMessageContent('  ', ['data:a']);
			expect(parts).toHaveLength(1);
			expect(parts[0].type).toBe('image_url');
		});
	});

	describe('supportsVision', () => {
		it('含 vision 返回 true（大小写不敏感）', () => {
			expect(supportsVision('vision,tools')).toBe(true);
			expect(supportsVision('Tools, Vision')).toBe(true);
		});

		it('未配置返回 null（与后端口径一致：放行不阻断）', () => {
			expect(supportsVision(null)).toBeNull();
			expect(supportsVision('')).toBeNull();
			expect(supportsVision('  ')).toBeNull();
			expect(supportsVision(undefined)).toBeNull();
		});

		it('配置但无 vision 返回 false', () => {
			expect(supportsVision('tools,function-call')).toBe(false);
		});
	});

	describe('readFileAsDataUri', () => {
		it('读取为 data URI 前缀', async () => {
			const dataUri = await readFileAsDataUri(makeImageFile());
			expect(dataUri.startsWith('data:image/png;base64,')).toBe(true);
		});
	});

	it('常量约束：张数上限为 4', () => {
		expect(CHAT_IMAGE_MAX_COUNT).toBe(4);
	});
});
