import { describe, expect, it } from 'vitest';
import { h } from 'vue';
import { mount } from '@vue/test-utils';
import IntentClassifierNode from '/$/workflow/components/custom-nodes/intent-classifier-node.vue';

/**
 * intent-classifier 重写后自身零外部依赖（useNode/inject/i18n 都在 base-node 内），
 * 故用 FakeBaseNode 捕获它透传给 base-node 的 props，即可验证多输出 Handle 生成逻辑。
 */
function mountWith(data: any) {
	let captured: any = {};
	const FakeBaseNode = {
		name: 'BaseNode',
		props: [
			'label',
			'selected',
			'incomplete',
			'isChild',
			'groupLabel',
			'hasTarget',
			'hasSource',
			'nodeHeight',
			'customOutputHandles'
		],
		setup(props: any) {
			captured = props;
			return () => h('div');
		}
	};
	mount(IntentClassifierNode, {
		props: { label: '意图分类', data },
		global: { stubs: { 'base-node': FakeBaseNode as any } }
	});
	return () => captured;
}

describe('workflow intent-classifier-node', () => {
	it('renders only the default branch when no intents configured', () => {
		const props = mountWith({ config: {} });
		const handles = props().customOutputHandles;
		expect(handles).toHaveLength(1);
		expect(handles[0]).toMatchObject({ id: 'default', label: '默认' });
		// totalCount = 1 → max(56, 1*28+28) = 56
		expect(props().nodeHeight).toBe(56);
	});

	it('builds one handle per intent plus a trailing default branch', () => {
		const props = mountWith({
			config: { intents: [{ id: 'a', name: '订票' }, { id: 'b', name: '退款' }] }
		});
		const handles = props().customOutputHandles;
		expect(handles).toHaveLength(3);
		// 🔒 数据兼容：intent 分支 Handle ID 必须保持 'intent_<id>'
		expect(handles[0].id).toBe('intent_a');
		expect(handles[1].id).toBe('intent_b');
		expect(handles[2].id).toBe('default');
		// label 取自 intent.name
		expect(handles[0].label).toBe('订票');
		expect(handles[1].label).toBe('退款');
		expect(handles[2].label).toBe('默认');
		// intent 分支 teal、默认分支灰
		expect(handles[0]).toMatchObject({
			labelClass: 'handle-label--intent',
			handleClass: 'handle-intent'
		});
		expect(handles[2]).toMatchObject({
			labelClass: 'handle-label--default',
			handleClass: 'handle-default'
		});
	});

	it('falls back Handle ID to index and label to I<n> when intent lacks id/name', () => {
		const props = mountWith({ config: { intents: [{ id: 'x' }, {}] } });
		const handles = props().customOutputHandles;
		expect(handles[0].id).toBe('intent_x');
		expect(handles[0].label).toBe('I1');
		// 无 id → 回退下标 i=1
		expect(handles[1].id).toBe('intent_1');
		expect(handles[1].label).toBe('I2');
	});

	it('distributes handles vertically by topPercent (totalCount = intents + 1)', () => {
		const props = mountWith({ config: { intents: [{ id: 'a' }, { id: 'b' }] } });
		const handles = props().customOutputHandles;
		// totalCount = 3 → (i+1)*100/(3+1) = 25/50/75
		expect(handles[0].topPercent).toBe(25);
		expect(handles[1].topPercent).toBe(50);
		expect(handles[2].topPercent).toBe(75);
	});

	it('grows nodeHeight with intent count', () => {
		const one = mountWith({ config: { intents: [{ id: 'a' }] } })().nodeHeight;
		const five = mountWith({
			config: { intents: Array.from({ length: 5 }, (_, i) => ({ id: i })) }
		})().nodeHeight;
		// nodeHeight = max(56, totalCount*28 + 28)
		expect(one).toBe(84); // totalCount=2 → 56 vs 84
		expect(five).toBe(196); // totalCount=6 → 196
	});

	it('forwards hasTarget/hasSource=false and label to base-node', () => {
		const props = mountWith({ config: {} });
		expect(props().hasTarget).toBe(true);
		expect(props().hasSource).toBe(false);
		expect(props().label).toBe('意图分类');
	});
});
