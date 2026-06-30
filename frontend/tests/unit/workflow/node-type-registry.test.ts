import { describe, expect, it } from 'vitest';
import { NODE_REGISTRY, getNodeMeta } from '/$/workflow/utils/node-type-registry';

describe('workflow node-type-registry', () => {
	// 冒烟测试：确认测试基建能加载 workflow 模块的纯数据导出，
	// 并锁住节点注册表的关键不变量（后续批次补 CSS / 重构时会复用）。
	it('registers all expected node types', () => {
		expect(NODE_REGISTRY.length).toBe(15);
		const types = NODE_REGISTRY.map(n => n.type);
		[
			'start',
			'end',
			'llm',
			'image_generator',
			'intent_classifier',
			'tool_executor',
			'condition',
			'switch',
			'loop_controller',
			'batch_processor',
			'human_input',
			'variable_assignment',
			'variable_transform',
			'tool',
			'loop_body_group'
		].forEach(t => expect(types).toContain(t));
	});

	it('has unique node types and colorClasses', () => {
		const types = NODE_REGISTRY.map(n => n.type);
		const classes = NODE_REGISTRY.map(n => n.colorClass);
		expect(new Set(types).size).toBe(types.length);
		expect(new Set(classes).size).toBe(classes.length);
	});

	it('marks only the legacy tool node as deprecated', () => {
		const deprecatedTypes = NODE_REGISTRY.filter(n => 'deprecated' in n).map(n => n.type);
		expect(deprecatedTypes).toEqual(['tool']);
	});

	it('keeps variable_assignment / variable_transform registered', () => {
		// 批次3 将为这两个节点补充 CSS 颜色类，此处锁住其注册不变量
		expect(getNodeMeta('variable_assignment').colorClass).toBe('node-variable_assignment');
		expect(getNodeMeta('variable_transform').colorClass).toBe('node-variable_transform');
	});

	it('falls back to an unknown-node meta for unregistered types', () => {
		const meta = getNodeMeta('not_a_real_node');
		expect(meta.type).toBe('not_a_real_node');
		expect(meta.colorClass).toBe('node-unknown');
	});
});
