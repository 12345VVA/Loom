import { describe, expect, it } from 'vitest';
import { findImageData } from '/$/ai/views/image-utils';

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
});
