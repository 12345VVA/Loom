import { describe, expect, it } from 'vitest';
import {
	buildDisplayItems,
	findImagesInData,
	isLikelyImageUrl,
	type ArtifactItem
} from '/$/workflow/utils/artifact-display';

// 展示派生用的恒等/标记转换，断言只关心调用位
const assetUrl = (raw: string) => `asset:${raw}`;
const formatJson = (raw: string) => `json:${raw}`;

function item(partial: Partial<ArtifactItem>): ArtifactItem {
	return { id: 1, fieldKey: 'f', assetType: 'text', ...partial };
}

describe('workflow artifact-display', () => {
	describe('isLikelyImageUrl', () => {
		it('recognizes uploads paths, image extensions and cloud CDN patterns', () => {
			expect(isLikelyImageUrl('/uploads/2026/01/a.png')).toBe(true);
			expect(isLikelyImageUrl('https://cdn.example.com/pic.jpg?sign=1')).toBe(true);
			expect(isLikelyImageUrl('https://bucket.tos-cn-beijing.volces.com/x.webp')).toBe(true);
			expect(isLikelyImageUrl('https://a.oss-cn-hangzhou.aliyuncs.com/y.gif')).toBe(true);
			expect(isLikelyImageUrl('https://x.myqcloud.com/z.avif')).toBe(true);
			expect(isLikelyImageUrl('https://arschip/doubao-img/1.jpeg')).toBe(true);
		});

		it('rejects plain text, multiline strings and non-image urls', () => {
			expect(isLikelyImageUrl('hello world')).toBe(false);
			expect(isLikelyImageUrl('line1\nline2')).toBe(false);
			expect(isLikelyImageUrl('https://example.com/page')).toBe(false);
			expect(isLikelyImageUrl('')).toBe(false);
		});
	});

	describe('findImagesInData', () => {
		it('walks nested objects/arrays and records field paths', () => {
			const found = findImagesInData({
				cover: 'https://cdn.example.com/a.png',
				gallery: ['https://cdn.example.com/b.jpg', 'text']
			});
			expect(found).toEqual([
				{ url: 'https://cdn.example.com/a.png', path: '.cover' },
				{ url: 'https://cdn.example.com/b.jpg', path: '.gallery.0' }
			]);
		});

		it('skips prompt-like keys and internal __src channels', () => {
			const found = findImagesInData({
				prompt: 'https://cdn.example.com/prompt.png',
				text: 'https://cdn.example.com/text.png',
				cover__src: 'https://cdn.example.com/tmp.png',
				cover: 'https://cdn.example.com/keep.png'
			});
			expect(found).toEqual([{ url: 'https://cdn.example.com/keep.png', path: '.cover' }]);
		});
	});

	describe('buildDisplayItems', () => {
		it('maps image artifacts through assetUrl with copyText kept raw', () => {
			const out = buildDisplayItems([item({ assetType: 'image', storageUrl: '/uploads/a.png' })], assetUrl, formatJson);
			expect(out).toHaveLength(1);
			expect(out[0]).toMatchObject({
				assetType: 'image',
				src: 'asset:/uploads/a.png',
				copyText: '/uploads/a.png'
			});
		});

		it('formats text artifacts and probes nested images inside JSON content', () => {
			const content = JSON.stringify({
				inner: ['https://cdn.example.com/nested.png'],
				note: '说明文字'
			});
			const out = buildDisplayItems([item({ id: 7, assetType: 'json', content })], assetUrl, formatJson);
			// 内嵌图片卡片 + 原 JSON 卡片并存
			expect(out).toHaveLength(2);
			expect(out[0]).toMatchObject({
				id: Number('7000'),
				assetType: 'image',
				src: 'asset:https://cdn.example.com/nested.png',
				fieldPath: 'f.inner.0'
			});
			expect(out[1]).toMatchObject({ id: 7, assetType: 'json', display: `json:${content}` });
		});

		it('deduplicates the same raw image url across artifacts and nested probes', () => {
			const url = 'https://cdn.example.com/dup.png';
			const out = buildDisplayItems(
				[
					item({ id: 1, assetType: 'image', storageUrl: url }),
					item({ id: 2, assetType: 'json', content: JSON.stringify({ img: url }) })
				],
				assetUrl,
				formatJson
			);
			const imageCards = out.filter(i => i.assetType === 'image');
			expect(imageCards).toHaveLength(1);
			expect(imageCards[0].id).toBe(1);
		});

		it('keeps the text card for non-json payloads without probing', () => {
			const out = buildDisplayItems([item({ id: 3, assetType: 'text', content: 'plain text' })], assetUrl, formatJson);
			expect(out).toHaveLength(1);
			expect(out[0]).toMatchObject({ id: 3, assetType: 'text', src: '', display: 'json:plain text' });
		});
	});
});
