import { describe, expect, it } from 'vitest';
import { mount } from '@vue/test-utils';
import { createI18n } from 'vue-i18n';
import LogJsonViewer from '/$/workflow/components/log-json-viewer.vue';

// vue-i18n：messages 留空，$t(key) 回退为 key 本身（zh-cn 原样显示中文 key）
const i18n = createI18n({
	legacy: false,
	locale: 'zh-cn',
	fallbackLocale: 'zh-cn',
	messages: { 'zh-cn': {} },
	missingWarn: false,
	fallbackWarn: false
});

// 浅渲染 Element Plus 组件；ElInput 渲染真实 input 以驱动 searchKey（v-model）
const stubs = {
	ElTag: { template: '<span class="tag"><slot /></span>' },
	ElButton: {
		emits: ['click'],
		template: '<button class="btn" @click="$emit(\'click\')"><slot /></button>'
	},
	ElInput: {
		props: ['modelValue'],
		emits: ['update:modelValue'],
		template: `<input class="search-input" :value="modelValue" @input="$emit('update:modelValue', $event.target.value)" />`
	},
	ElDialog: { template: '<div class="dialog"><slot /></div>' },
	ElTooltip: { template: '<span class="tooltip"><slot /></span>' }
};

function mountViewer(props: Record<string, unknown>) {
	return mount(LogJsonViewer, {
		props: props as never,
		global: { plugins: [i18n], stubs }
	});
}

function codeHtml(w: ReturnType<typeof mountViewer>): string {
	return (w.element.querySelector('.highlight-code') as HTMLElement).innerHTML;
}

describe('workflow LogJsonViewer search highlight', () => {
	it('wraps matches in <mark> inside text tokens', async () => {
		const w = mountViewer({ value: { name: 'x' }, searchable: true, showHeader: true });
		await w.find('input.search-input').setValue('name');
		expect(codeHtml(w)).toContain('<mark class="json-hl-match">name</mark>');
	});

	it('keeps tag structure intact when searching for markup words (span)', async () => {
		const w = mountViewer({ value: { span: 'value' }, searchable: true, showHeader: true });
		await w.find('input.search-input').setValue('span');
		const html = codeHtml(w);
		// mark 只应出现在文本节点内：修复前对已注入语法 span 的 HTML 整串替换，
		// 会把 <span/class 等标记名包进 mark 导致标签碎裂
		expect(html).toMatch(/<mark class="json-hl-match">span<\/mark>/);
		expect(html).not.toMatch(/<[^>]*<mark/);
	});

	it('keeps tag structure intact when searching for "class"', async () => {
		const w = mountViewer({ value: { class: 'a' }, searchable: true, showHeader: true });
		await w.find('input.search-input').setValue('class');
		const html = codeHtml(w);
		expect(html).toMatch(/<mark class="json-hl-match">class<\/mark>/);
		expect(html).not.toMatch(/<[^>]*<mark/);
	});

	it('renders no mark when search is empty', () => {
		const w = mountViewer({ value: { name: 'x' }, searchable: true, showHeader: true });
		expect(codeHtml(w)).not.toContain('<mark');
	});
});
