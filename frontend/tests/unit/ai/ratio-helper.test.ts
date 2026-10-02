import { describe, expect, it } from 'vitest';
import { COMMON_RATIOS, isRatioActive, selectBestRatioSize } from '/$/ai/utils/ratio-helper';

describe('ratio-helper utils', () => {
	it('defines standard common ratios', () => {
		expect(COMMON_RATIOS.length).toBe(5);
		expect(COMMON_RATIOS.map(r => r.key)).toEqual(['1:1', '16:9', '9:16', '4:3', '3:4']);
	});

	it('checks isRatioActive correctly', () => {
		expect(isRatioActive('1:1', '1:1')).toBe(true);
		expect(isRatioActive('1024x1024', '1:1')).toBe(true);
		expect(isRatioActive('1280x720(16:9)', '16:9')).toBe(true);
		expect(isRatioActive('1920x1080', '16:9')).toBe(true);
		expect(isRatioActive('1080x1920', '9:16')).toBe(true);
		expect(isRatioActive('1024x768', '4:3')).toBe(true);
		expect(isRatioActive('768x1024', '3:4')).toBe(true);
		expect(isRatioActive('1024x1024', '16:9')).toBe(false);
		expect(isRatioActive('', '1:1')).toBe(false);
		expect(isRatioActive(null, '1:1')).toBe(false);
	});

	it('selects best ratio size from options', () => {
		const options = [
			{ label: '1024x1024 (1:1)', value: '1024x1024' },
			{ label: '1280x720 (16:9)', value: '1280x720' },
			{ label: '720x1280 (9:16)', value: '720x1280' },
			{ label: '自定义 1:1', value: '1:1' }
		];

		// 精确匹配
		expect(selectBestRatioSize(options, '1:1')).toBe('1:1');

		// 标签匹配
		expect(selectBestRatioSize(options.slice(0, 3), '16:9')).toBe('1280x720');

		// 数值匹配
		const numOptions = [
			{ label: '方图', value: '512x512' },
			{ label: '宽图', value: '1920x1080' }
		];
		expect(selectBestRatioSize(numOptions, '1:1')).toBe('512x512');
		expect(selectBestRatioSize(numOptions, '16:9')).toBe('1920x1080');

		// 空选项处理
		expect(selectBestRatioSize([], '1:1')).toBeNull();
	});
});
