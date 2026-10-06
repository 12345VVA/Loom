import { describe, expect, it } from 'vitest';
import {
	buildStartInputsTemplate,
	parseStartInputVariables
} from '/$/workflow/utils/start-inputs';

describe('start-inputs', () => {
	describe('parseStartInputVariables', () => {
		it('兼容旧写法（纯字符串数组）', () => {
			const vars = parseStartInputVariables(['query', 'topic']);
			expect(vars).toEqual([
				{ name: 'query', hasDefault: false, defaultValue: undefined },
				{ name: 'topic', hasDefault: false, defaultValue: undefined }
			]);
		});

		it('解析新写法（带默认值对象）', () => {
			const vars = parseStartInputVariables([
				{ name: 'input_query' },
				{ name: 'image_count', default: 10 }
			]);
			expect(vars).toEqual([
				{ name: 'input_query', hasDefault: false, defaultValue: undefined },
				{ name: 'image_count', hasDefault: true, defaultValue: 10 }
			]);
		});

		it('显式默认 null 与「未声明默认值」可区分', () => {
			const vars = parseStartInputVariables([{ name: 'a', default: null }]);
			expect(vars[0].hasDefault).toBe(true);
			expect(vars[0].defaultValue).toBeNull();
		});

		it('忽略空名、非数组、非法项', () => {
			expect(parseStartInputVariables(undefined)).toEqual([]);
			expect(parseStartInputVariables('query')).toEqual([]);
			expect(parseStartInputVariables(['', '  ', { name: '' }, 42])).toEqual([]);
		});
	});

	describe('buildStartInputsTemplate', () => {
		it('有默认值用默认值，否则留空串', () => {
			const tpl = buildStartInputsTemplate([
				{ name: 'input_query' },
				{ name: 'image_count', default: 10 }
			]);
			expect(tpl).toEqual({ input_query: '', image_count: 10 });
		});

		it('无声明时返回空对象', () => {
			expect(buildStartInputsTemplate(undefined)).toEqual({});
		});
	});
});
