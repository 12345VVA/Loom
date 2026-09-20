import { describe, expect, it } from 'vitest';
import { extractImageItems, findImageData } from '/$/ai/utils/image-utils';

describe('findImageData', () => {
	it('returns empty for nullish input', () => {
		expect(findImageData(null)).toEqual([]);
		expect(findImageData(undefined)).toEqual([]);
	});

	it('parses JSON string and extracts the nested array', () => {
		expect(findImageData(JSON.stringify([{ a: 1 }]))).toEqual([{ a: 1 }]);
	});

	it('returns arrays directly', () => {
		expect(findImageData([1, 2, 3])).toEqual([1, 2, 3]);
	});

	it('extracts from common wrapper shapes (.data / .result / .output / .images)', () => {
		expect(findImageData({ data: [{ x: 1 }] })).toEqual([{ x: 1 }]);
		expect(findImageData({ result: { data: [{ y: 2 }] } })).toEqual([{ y: 2 }]);
		expect(findImageData({ output: [{ z: 3 }] })).toEqual([{ z: 3 }]);
		expect(findImageData({ images: ['img1'] })).toEqual(['img1']);
	});

	it('returns [] for invalid JSON string', () => {
		expect(findImageData('{not json')).toEqual([]);
	});

	// [P1 回归] 超深嵌套不再栈溢出（深度限制）
	it('does not stack-overflow on pathologically deep nesting', () => {
		let deep: any = { images: ['bottom'] };
		for (let i = 0; i < 100; i++) deep = { result: deep };
		expect(() => findImageData(deep)).not.toThrow();
		// 5 层内未触达 images → 返回 []
		expect(findImageData(deep)).toEqual([]);
	});

	// [P1 回归] 循环引用不再无限递归
	it('does not loop forever on circular references', () => {
		const a: any = { result: null };
		a.result = a;
		expect(() => findImageData(a)).not.toThrow();
	});

	// [P1 回归] resultPayload 包装形态（旧 profile/task 拷贝缺失的分支）
	it('extracts from resultPayload wrapper', () => {
		expect(findImageData({ resultPayload: { data: [{ p: 1 }] } })).toEqual([{ p: 1 }]);
	});
});

describe('extractImageItems', () => {
	it('maps url items', () => {
		expect(extractImageItems({ data: [{ url: 'http://x/a.png' }] })).toEqual([
			{ src: 'http://x/a.png', value: 'http://x/a.png', url: 'http://x/a.png' }
		]);
	});

	it('maps image_url / imageUrl / image aliases', () => {
		expect(extractImageItems({ data: [{ image_url: 'http://x/b.png' }] })[0]?.src).toBe(
			'http://x/b.png'
		);
		expect(extractImageItems({ data: [{ imageUrl: 'http://x/c.png' }] })[0]?.src).toBe(
			'http://x/c.png'
		);
		expect(extractImageItems({ data: [{ image: 'http://x/d.png' }] })[0]?.src).toBe(
			'http://x/d.png'
		);
	});

	it('wraps raw base64 into data URI', () => {
		const items = extractImageItems({ data: [{ b64_json: 'abc123' }] });
		expect(items[0]?.src).toBe('data:image/png;base64,abc123');
		expect(items[0]?.value).toBe('abc123');
	});

	it('keeps already-encoded data URI as-is', () => {
		const uri = 'data:image/png;base64,xyz';
		expect(extractImageItems({ data: [{ b64_json: uri }] })[0]?.src).toBe(uri);
	});

	it('filters out items without url or base64', () => {
		expect(extractImageItems({ data: [{ foo: 1 }, { url: 'http://x/e.png' }] })).toHaveLength(1);
	});
});
