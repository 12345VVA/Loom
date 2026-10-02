import { describe, expect, it, vi } from 'vitest';
import { mount } from '@vue/test-utils';
import { createI18n } from 'vue-i18n';

// 组件经 use-asset-url → /@/cool 传递依赖 @cool-vue/crud（UMD 包在 vitest ESM 环境加载崩溃），
// 与其余单测一致地 stub 框架层（见 tests/unit/media/use-asset-url.test.ts）
vi.mock('/@/cool', () => ({
	useCool: () => ({
		service: {
			media: {
				asset: {
					downloadToken: vi.fn().mockResolvedValue({ token: 'mocked_token', expire: 7200 })
				}
			}
		}
	})
}));

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
		// 新版 nodeType 渲染中文类型标签（llm → 大模型），不再显示英文原文
		expect(w.text()).toContain('大模型');
	});

	it('shows status tag only when status prop is provided', () => {
		const withStatus = mountDrawer({ visible: true, items: [], status: 'running' });
		// 状态胶囊显示中文映射（running → 运行中），旧版"状态："前缀已废弃
		expect(withStatus.text()).toContain('运行中');

		const noStatus = mountDrawer({ visible: true, items: [] });
		expect(noStatus.text()).not.toContain('运行中');
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

	it('hides toolbar when no status and empty items', () => {
		const w = mountDrawer({ visible: true, items: [], emptyText: '空' });
		expect(w.text()).toContain('空');
		// 工具栏 v-if="items.length > 0"：空态不渲染（旧断言按 button 计数，
		// 会误计入 stub 之外残留的按钮，改为按渲染文本判断）
		expect(w.text()).not.toContain('展开全部');
		expect(w.text()).not.toContain('全部状态');
	});
});
