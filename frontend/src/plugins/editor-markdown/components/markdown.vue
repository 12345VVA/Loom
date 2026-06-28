<template>
	<div
		ref="containerRef"
		class="cl-editor-markdown"
		:class="{ disabled, 'is-preview': onlyPreview, simple }"
	>
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
			v-model:preview="showPreview"
			:readOnly="disabled || preview"
			:noMermaid="true"
			:noKatex="true"
			:noEcharts="true"
			:placeholder="placeholder || t('开始编写 Markdown...')"
			:toolbarsExclude="excludedToolbars"
			:style="{ height: parsePx(height) }"
			@onUploadImg="onUploadImg"
		/>

		<!-- 变量插入悬浮按钮 -->
		<el-popover
			v-if="
				!disabled &&
				!preview &&
				!onlyPreview &&
				(upstreamOutputVars?.length || loopContextVars?.length)
			"
			placement="bottom-end"
			:width="280"
			trigger="click"
		>
			<template #reference>
				<el-button class="md-var-btn" size="small" :icon="Link" plain>{{
					$t('变量')
				}}</el-button>
			</template>
			<div class="variable-list">
				<div v-if="loopContextVars?.length" class="var-group">
					<div class="var-group-title">{{ $t('循环上下文') }}</div>
					<div
						v-for="v in loopContextVars"
						:key="v.key"
						class="var-item"
						@click="insertVariable(v.refText)"
					>
						<span>{{ v.display }}</span>
						<small>{{ v.nodeLabel }}</small>
					</div>
				</div>
				<div v-if="upstreamOutputVars?.length" class="var-group">
					<div class="var-group-title">{{ $t('上游输出') }}</div>
					<div
						v-for="v in upstreamOutputVars"
						:key="v.key"
						class="var-item"
						@click="insertVariable(v.refText)"
					>
						<span>{{ v.display }}</span>
						<small>{{ v.nodeLabel }}</small>
					</div>
				</div>
			</div>
		</el-popover>
	</div>
</template>

<script lang="ts" setup>
defineOptions({
	name: 'cl-editor-markdown'
});

import { ref, computed, watch } from 'vue';
import { MdEditor, MdPreview, type ToolbarNames } from 'md-editor-v3';
import 'md-editor-v3/lib/style.css';
import { useDark } from '@vueuse/core';
import { parsePx } from '/@/cool/utils';
import { useUpload } from '/#/upload/hooks';
import { ElMessage } from 'element-plus';
import { useI18n } from 'vue-i18n';
import { inject } from 'vue';
import { Link } from '@element-plus/icons-vue';
import type { InjectionKey, Ref } from 'vue';

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

const containerRef = ref<HTMLElement>();
const id = ref('cl-md-' + Math.random().toString(36).substring(2, 9));

// 跨模块解耦：使用相同的注入 Key 类型，避免硬依赖 workflow 模块
const UPSTREAM_OUTPUT_VARS_KEY = 'upstreamOutputVars' as unknown as InjectionKey<Ref<any[]>>;
const LOOP_CONTEXT_VARS_KEY = 'loopContextVars' as unknown as InjectionKey<Ref<any[]>>;

const upstreamOutputVars = inject(UPSTREAM_OUTPUT_VARS_KEY, ref([]));
const loopContextVars = inject(LOOP_CONTEXT_VARS_KEY, ref([]));

const value = computed({
	get: () => props.modelValue || '',
	set: val => {
		emit('update:modelValue', val);
		emit('change', val);
	}
});

// 局部状态管理 md-editor 的预览区是否展示
const showPreview = ref(props.preview || false);

watch(
	() => props.preview,
	val => {
		showPreview.value = val || false;
	}
);

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

function insertVariable(refText: string) {
	// md-editor-v3 的内置插入方法
	const editorEl = containerRef.value?.querySelector('textarea');
	if (editorEl) {
		const start = editorEl.selectionStart || 0;
		const end = editorEl.selectionEnd || 0;
		const val = value.value;
		const newVal = val.substring(0, start) + refText + val.substring(end);
		setValue(newVal);

		// 稍微延迟以确保视图更新后恢复焦点
		setTimeout(() => {
			const newEditorEl = containerRef.value?.querySelector('textarea');
			if (newEditorEl) {
				newEditorEl.focus();
				newEditorEl.setSelectionRange(start + refText.length, start + refText.length);
			}
		}, 0);
	} else {
		setValue(value.value + refText);
	}
}

defineExpose({ getValue, setValue, formatCode: () => {} });
</script>

<style lang="scss" scoped>
@use '/@/modules/workflow/components/variable-list.scss';

.cl-editor-markdown {
	position: relative;
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

	.md-var-btn {
		position: absolute;
		right: 8px;
		top: 6px;
		z-index: 10;
	}
}
</style>
