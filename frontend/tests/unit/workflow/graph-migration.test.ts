import { describe, expect, it } from 'vitest';
import { migrateLoadedElements } from '/$/workflow/utils/graph-migration';

describe('migrateLoadedElements', () => {
	describe('tool_executor arguments 编辑态适配', () => {
		it('把 arguments 对象序列化为 argumentsJson 字符串', () => {
			const els = [{ id: 't1', type: 'tool_executor', data: { config: { arguments: { a: 1 } } } }];
			migrateLoadedElements(els);
			expect(els[0].data.config.argumentsJson).toBe(JSON.stringify({ a: 1 }, null, 2));
		});

		it('已有 argumentsJson 时不覆盖（幂等）', () => {
			const els = [
				{ id: 't1', type: 'tool_executor', data: { config: { argumentsJson: '{"x":1}' } } }
			];
			migrateLoadedElements(els);
			expect(els[0].data.config.argumentsJson).toBe('{"x":1}');
		});

		it('非 tool_executor 节点不受影响', () => {
			const els = [{ id: 'l1', type: 'llm', data: { config: {} } }];
			migrateLoadedElements(els);
			expect(els[0].data.config.argumentsJson).toBeUndefined();
		});
	});

	describe('switch/intent 稳定 id 补全', () => {
		it('为 switch.cases 缺 id 的条目补 id，已有 id 不动', () => {
			const els = [
				{
					id: 's1',
					type: 'switch',
					data: { config: { cases: [{ value: 'a' }, { id: 'keep', value: 'b' }] } }
				}
			];
			migrateLoadedElements(els);
			expect(els[0].data.config.cases[0].id).toBeTruthy();
			expect(els[0].data.config.cases[1].id).toBe('keep');
		});

		it('为 intent_classifier.intents 缺 id 的条目补 id', () => {
			const els = [
				{ id: 'i1', type: 'intent_classifier', data: { config: { intents: [{ name: 'x' }] } } }
			];
			migrateLoadedElements(els);
			expect(els[0].data.config.intents[0].id).toBeTruthy();
		});

		it('幂等：重复迁移不改变已补的 id', () => {
			const els = [{ id: 's1', type: 'switch', data: { config: { cases: [{ value: 'a' }] } } }];
			migrateLoadedElements(els);
			const id1 = els[0].data.config.cases[0].id;
			migrateLoadedElements(els);
			expect(els[0].data.config.cases[0].id).toBe(id1);
		});
	});

	it('跳过边元素（含 source 字段）', () => {
		const edge = { id: 'e1', source: 'a', target: 'b' };
		migrateLoadedElements([edge]);
		expect(edge).toEqual({ id: 'e1', source: 'a', target: 'b' });
	});

	// 回归保护：旧版本兼容代码已激进清理，确认这些默认值补全不会复活
	it('不再补 start 缺失的 inputVariables（旧兼容已删）', () => {
		const els = [{ id: 'st', type: 'start', data: { config: {} } }];
		migrateLoadedElements(els);
		expect(els[0].data.config.inputVariables).toBeUndefined();
	});

	it('不再补 end 缺失的 outputFormat/outputFields（旧兼容已删）', () => {
		const els = [{ id: 'ed', type: 'end', data: { config: {} } }];
		migrateLoadedElements(els);
		expect(els[0].data.config.outputFormat).toBeUndefined();
		expect(els[0].data.config.outputFields).toBeUndefined();
	});

	it('不再补 llm 缺失的 jsonFields（旧兼容已删）', () => {
		const els = [{ id: 'l1', type: 'llm', data: { config: {} } }];
		migrateLoadedElements(els);
		expect(els[0].data.config.jsonFields).toBeUndefined();
	});
});
