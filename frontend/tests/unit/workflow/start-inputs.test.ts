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
				{ name: 'query', hasDefault: false, defaultValue: undefined, type: 'string' },
				{ name: 'topic', hasDefault: false, defaultValue: undefined, type: 'string' }
			]);
		});

		it('解析新写法（带默认值对象）', () => {
			const vars = parseStartInputVariables([
				{ name: 'input_query' },
				{ name: 'image_count', default: 10 }
			]);
			expect(vars).toEqual([
				{ name: 'input_query', hasDefault: false, defaultValue: undefined, type: 'string' },
				{ name: 'image_count', hasDefault: true, defaultValue: 10, type: 'string' }
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

		it('WFI-1b：v2 type 声明透传，非法 type 回落 string', () => {
			const vars = parseStartInputVariables([
				{ name: 'input_image', type: 'image' },
				{ name: 'count', type: 'number' },
				{ name: 'flag', type: 'boolean' },
				{ name: 'weird', type: 'audio' }
			]);
			expect(vars.map(v => v.type)).toEqual(['image', 'number', 'boolean', 'string']);
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

		it('WFI-1b：未声明默认值时按类型产初值（image→空串、number→0、boolean→false）', () => {
			const tpl = buildStartInputsTemplate([
				{ name: 'input_image', type: 'image' },
				{ name: 'count', type: 'number' },
				{ name: 'flag', type: 'boolean' }
			]);
			expect(tpl).toEqual({ input_image: '', count: 0, flag: false });
		});
	});
});
