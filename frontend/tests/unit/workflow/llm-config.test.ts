import { describe, expect, it, vi } from 'vitest';
import { mount } from '@vue/test-utils';
import { createI18n } from 'vue-i18n';

// 组件依赖链含框架层（/$/ai 的 utils 经 cool 体系），统一 mock（见 log-drawer.test.ts 先例）
vi.mock('/@/cool', () => ({
	useCool: () => ({ service: {} })
}));

import LlmConfig from '/$/workflow/components/node-configs/llm-config.vue';

const i18n = createI18n({
	legacy: false,
	locale: 'zh-cn',
	fallbackLocale: 'zh-cn',
	messages: { 'zh-cn': {} },
	missingWarn: false,
	fallbackWarn: false
});

const RadioGroupStub = {
	name: 'ElRadioGroup',
	props: ['modelValue'],
	emits: ['update:modelValue'],
	template: '<div class="rg" :data-val="modelValue"><slot /></div>'
};
const SelectStub = {
	name: 'ElSelect',
	props: ['modelValue', 'multiple', 'placeholder'],
	emits: ['update:modelValue'],
	template: '<div class="sel"><slot /></div>'
};
const OptionStub = {
	name: 'ElOption',
	props: ['label', 'value'],
	template: '<span class="opt" />'
};
const stubs = {
	NodeConfigSection: { props: ['title'], template: '<section><h4>{{ title }}</h4><slot name="actions" /><slot /></section>' },
	ClEditorMarkdown: { props: ['modelValue'], template: '<div class="md" />' },
	ClJsonTreeEditor: { template: '<div class="json-editor" />' },
	ElFormItem: { template: '<div class="fi"><slot /></div>' },
	ElRadioGroup: RadioGroupStub,
	ElRadioButton: { props: ['value'], template: '<span class="rb" />' },
	ElSelect: SelectStub,
	ElOption: OptionStub,
	ElInput: { props: ['modelValue', 'placeholder'], emits: ['update:modelValue'], template: '<input class="ipt" />' },
	ElDropdown: { template: '<div class="dd"><slot /><slot name="dropdown" /></div>' },
	ElDropdownMenu: { template: '<div><slot /></div>' },
	ElDropdownItem: { template: '<div><slot /></div>' },
	ElTooltip: { template: '<div><slot /></div>' },
	ElIcon: { template: '<span><slot /></span>' }
};

// 与 llm-config.vue 的 LlmNodeConfig / Eps.profile / upstreamVariables prop 同形；
// tests/ 不在 tsconfig include 内，故用本地 stub（勿引用 Eps 全局命名空间）
type LlmNodeConfigStub = {
	modelProfileCode?: string;
	systemPromptTemplate?: string;
	promptTemplate?: string;
	imageVariables?: string[];
	imageTemplate?: string;
	outputFormat?: string;
	jsonFields?: unknown[];
	outputVariable?: string;
};

type LlmProfileStub = { code?: string; name?: string; modelCapabilities?: string };

type LlmUpstreamVariableStub = { variableName: string; nodeLabel?: string; variableType?: string };

function mountWith(
	config: LlmNodeConfigStub,
	profiles: LlmProfileStub[] = [],
	upstreamVariables: LlmUpstreamVariableStub[] = []
) {
	return mount(LlmConfig, {
		props: { modelValue: config, profiles, upstreamVariables } as never,
		global: { plugins: [i18n], stubs }
	});
}

describe('workflow llm-config 多模态图片输入（WFI-2d）', () => {
	it('无任何绑定时为 none 模式，不渲染变量选择与模板输入', () => {
		const w = mountWith({ modelProfileCode: 'p1', promptTemplate: 'x' });
		expect(w.find('.rg').attributes('data-val')).toBe('none');
		expect(w.findAll('.sel').length).toBe(1); // 仅模型 profile 的 select
		expect(w.find('.ipt[placeholder="模板字符串，例如：{image_url}"]').exists()).toBe(false);
	});

	it('imageVariables 非空 → variable 模式，图片多选 select 渲染', () => {
		const w = mountWith({ modelProfileCode: 'p1', imageVariables: ['input_image'] });
		expect(w.find('.rg').attributes('data-val')).toBe('variable');
		// 模型 profile select + 图片变量 select 各一
		expect(w.findAll('.sel').length).toBe(2);
	});

	it('切换模式清空互斥键：variable → template 清空 imageVariables，再切 none 清空 imageTemplate', async () => {
		const config: LlmNodeConfigStub = {
			modelProfileCode: 'p1',
			imageVariables: ['input_image'],
			imageTemplate: ''
		};
		const w = mountWith(config);

		await w.findComponent(RadioGroupStub).vm.$emit('update:modelValue', 'template');
		expect(config.imageVariables).toEqual([]);
		// 重新 find：重渲染后旧 vnode 引用的属性不更新
		expect(w.find('.rg').attributes('data-val')).toBe('template');

		// 手动填入模板串后切回 none：模板键被清空
		config.imageTemplate = '{image_url}';
		await w.findComponent(RadioGroupStub).vm.$emit('update:modelValue', 'none');
		expect(config.imageTemplate).toBe('');
	});

	it('图片变量选项优先列 variableType=image 的上游变量', () => {
		// variable 模式（imageVariables 非空）才会渲染变量下拉与选项
		const w = mountWith(
			{ modelProfileCode: 'p1', imageVariables: ['input_image'] },
			[],
			[
				{ variableName: 'input_image', nodeLabel: '开始', variableType: 'image' },
				{ variableName: 'query', nodeLabel: '开始', variableType: 'string' },
				{ variableName: 'cover', nodeLabel: '生图', variableType: 'image' }
			]
		);
		const labels = w.findAllComponents(OptionStub).map(o => o.props('label'));
		expect(labels).toContain('开始 / input_image');
		expect(labels).toContain('生图 / cover');
		expect(labels).not.toContain('开始 / query');
	});

	it('profile 能力标签不含 vision 时渲染软警示；有 vision 或无能力信息不渲染', () => {
		const noVision = mountWith(
			{ modelProfileCode: 'p1' },
			[{ code: 'p1', name: 'P1', modelCapabilities: 'chat,tools' }]
		);
		expect(noVision.text()).toContain('当前模型可能不支持视觉输入');

		const hasVision = mountWith(
			{ modelProfileCode: 'p1' },
			[{ code: 'p1', name: 'P1', modelCapabilities: 'chat,vision' }]
		);
		expect(hasVision.text()).not.toContain('当前模型可能不支持视觉输入');

		const noCaps = mountWith({ modelProfileCode: 'p1' }, [{ code: 'p1', name: 'P1' }]);
		expect(noCaps.text()).not.toContain('当前模型可能不支持视觉输入');
	});
});
