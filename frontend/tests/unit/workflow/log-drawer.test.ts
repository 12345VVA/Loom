import { describe, expect, it } from 'vitest';
import { mount } from '@vue/test-utils';
import { createI18n } from 'vue-i18n';
import LogDrawer from '/$/workflow/components/log-drawer.vue';

// vue-i18n：messages 留空，$t(key) 回退为 key 本身（zh-cn 原样显示中文 key）
const i18n = createI18n({
	legacy: false,
	locale: 'zh-cn',
	fallbackLocale: 'zh-cn',
	messages: { 'zh-cn': {} },
	missingWarn: false,
	fallbackWarn: false
});

// 浅渲染 Element Plus 组件：el-drawer 渲染 slot 内容（避免 teleport），按钮透传 click
const stubs = {
	ElDrawer: { template: '<div class="drawer"><slot /></div>' },
	ElTimeline: { template: '<div class="timeline"><slot /></div>' },
	ElTimelineItem: { template: '<div class="item"><slot /></div>' },
	ElCard: { template: '<div class="card"><slot name="header" /><slot /></div>' },
	ElEmpty: {
		template: '<div class="empty">{{ description }}</div>',
		props: ['description']
	},
	ElTag: { template: '<span class="tag"><slot /></span>' },
	ElButton: {
		emits: ['click'],
		template: '<button class="btn" @click="$emit(\'click\')"><slot /></button>'
	},
	ElIcon: { template: '<span class="icon"><slot /></span>' }
};

function mountDrawer(props: Record<string, unknown>) {
	return mount(LogDrawer, {
		props: props as never,
		global: { plugins: [i18n], stubs }
	});
}

describe('workflow LogDrawer', () => {
	it('renders emptyText when items is empty', () => {
		const w = mountDrawer({ visible: true, items: [], emptyText: '暂无记录' });
		expect(w.text()).toContain('暂无记录');
	});

	it('renders nodeName / nodeType for each log item', () => {
		const w = mountDrawer({
			visible: true,
			items: [
				{
					nodeName: 'LLM节点',
					nodeType: 'llm',
					status: 'success',
					createTime: '2026-06-30T10:00:00Z'
				}
			]
		});
		expect(w.text()).toContain('LLM节点');
		expect(w.text()).toContain('llm');
	});

	it('shows status tag only when status prop is provided', () => {
		const withStatus = mountDrawer({ visible: true, items: [], status: 'running' });
		expect(withStatus.text()).toContain('状态：');

		const noStatus = mountDrawer({ visible: true, items: [] });
		expect(noStatus.text()).not.toContain('状态：');
	});

	it('emits expand-all / collapse-all when toolbar buttons clicked', async () => {
		const w = mountDrawer({
			visible: true,
			items: [{ nodeName: 'N', status: 'success' }],
			status: 'running'
		});
		const buttons = w.findAll('button');
		const expandBtn = buttons.find(b => b.text().includes('展开全部'));
		const collapseBtn = buttons.find(b => b.text().includes('折叠全部'));
		expect(expandBtn).toBeTruthy();
		expect(collapseBtn).toBeTruthy();

		await expandBtn!.trigger('click');
		expect(w.emitted('expand-all')).toBeTruthy();

		await collapseBtn!.trigger('click');
		expect(w.emitted('collapse-all')).toBeTruthy();
	});

	it('hides toolbar entirely when no status and no items', () => {
		const w = mountDrawer({ visible: true, items: [], emptyText: '空' });
		// 无 status 且 items 为空 → 工具条（展开/折叠按钮）不渲染
		expect(w.findAll('button').length).toBe(0);
	});
});
