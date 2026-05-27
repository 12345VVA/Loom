<template>
	<div class="cl-editor-markdown" :class="{ disabled, 'is-preview': onlyPreview, simple }">
		<!-- 纯渲染模式 -->
		<md-preview
			v-if="onlyPreview"
			:modelValue="value"
			:theme="isDark ? 'dark' : 'light'"
			:editorId="id"
		/>

		<!-- 编辑器模式 -->
		<md-editor
			v-else
			v-model="value"
			:theme="isDark ? 'dark' : 'light'"
			:editorId="id"
			:preview="showPreview"
			:readOnly="disabled || preview"
			:noMermaid="true"
			:noKatex="true"
			:noEcharts="true"
			:placeholder="placeholder || t('开始编写 Markdown...')"
			:toolbarsExclude="excludedToolbars"
			:style="{ height: parsePx(height) }"
			@onUploadImg="onUploadImg"
		/>
	</div>
</template>

<script lang="ts" setup>
defineOptions({
	name: 'cl-editor-markdown'
});

import { ref, computed } from 'vue';
import { MdEditor, MdPreview, type ToolbarNames } from 'md-editor-v3';
import 'md-editor-v3/lib/style.css';
import { useDark } from '@vueuse/core';
import { parsePx } from '/@/cool/utils';
import { useUpload } from '/#/upload/hooks';
import { ElMessage } from 'element-plus';
import { useI18n } from 'vue-i18n';

const props = defineProps({
	modelValue: {
		type: String,
		default: ''
	},
	height: {
		type: [String, Number],
		default: 400
	},
	disabled: Boolean,
	preview: Boolean,
	onlyPreview: Boolean,
	simple: Boolean,
	placeholder: {
		type: String,
		default: ''
	}
});

const emit = defineEmits(['update:modelValue', 'change']);

const { t } = useI18n();
const isDark = useDark();
const { toUpload } = useUpload();

const id = ref('cl-md-' + Math.random().toString(36).substring(2, 9));

const value = computed({
	get: () => props.modelValue || '',
	set: val => {
		emit('update:modelValue', val);
		emit('change', val);
	}
});

// preview 模式：编辑器只读 + 隐藏编辑工具栏
const showPreview = computed(() => props.preview || undefined);

// 不常用按钮，始终隐藏
const alwaysExclude: ToolbarNames[] = [
	'sub',
	'sup',
	'task',
	'prettier',
	'github',
	'catalog',
	'htmlPreview',
	'save'
];

// simple 模式：仅保留核心工具（加粗、斜体、行内代码、链接、图片、全屏、预览）
const simpleExclude: ToolbarNames[] = [
	'underline',
	'title',
	'strikeThrough',
	'quote',
	'unorderedList',
	'orderedList',
	'code',
	'table',
	'mermaid',
	'katex',
	'revoke',
	'next',
	'pageFullscreen',
	'previewOnly',
	'='
];

// preview 模式额外隐藏编辑类按钮
const previewExclude: ToolbarNames[] = [
	'bold',
	'underline',
	'italic',
	'title',
	'strikeThrough',
	'quote',
	'unorderedList',
	'orderedList',
	'codeRow',
	'code',
	'link',
	'image',
	'table',
	'mermaid',
	'katex',
	'revoke',
	'next',
	'pageFullscreen',
	'fullscreen'
];

const excludedToolbars = computed<ToolbarNames[]>(() => {
	const list = [...alwaysExclude];
	if (props.simple) list.push(...simpleExclude);
	if (props.preview) list.push(...previewExclude);
	return list;
});

// 图片上传
async function onUploadImg(files: File[], callback: (urls: string[]) => void) {
	try {
		const urls = await Promise.all(
			files.map(async file => {
				const res = await toUpload(file);
				return res.url;
			})
		);
		callback(urls);
	} catch (err: any) {
		ElMessage.error(t('图片上传失败'));
		console.error('[cl-editor-markdown] upload error:', err);
	}
}

function getValue(): string {
	return value.value;
}

function setValue(val: string) {
	emit('update:modelValue', val);
	emit('change', val);
}

defineExpose({ getValue, setValue, formatCode: () => {} });
</script>

<style lang="scss" scoped>
.cl-editor-markdown {
	border: 1px solid var(--el-border-color);
	border-radius: var(--el-border-radius-base);
	overflow: hidden;
	box-sizing: border-box;
	width: 100%;
	transition: border-color 0.2s;

	&:focus-within {
		border-color: var(--el-color-primary);
	}

	:deep(.md-editor) {
		border: none;
		background-color: var(--el-bg-color);
	}

	// 方案一：工具栏单行 + 横向滚动
	:deep(.md-editor-toolbar-wrapper) {
		overflow-x: auto;
		overflow-y: hidden;
		scrollbar-width: thin;
	}

	:deep(.md-editor-toolbar-wrapper::-webkit-scrollbar) {
		height: 3px !important;
	}

	:deep(.md-editor-toolbar-left) {
		flex-wrap: nowrap;
	}

	&.disabled {
		background-color: var(--el-disabled-bg-color);

		:deep(.md-editor) {
			background-color: var(--el-disabled-bg-color);
		}
	}

	&.is-preview {
		border: none;
		background: transparent;
	}
}
</style>
