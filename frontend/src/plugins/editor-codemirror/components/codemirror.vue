<template>
	<div class="cl-editor-codemirror" :class="{ disabled, 'is-preview': preview }">
		<div v-if="!preview" class="cl-editor-codemirror__toolbar">
			<el-button text size="small" @click="format">{{ t('格式化') }}</el-button>
			<el-button text size="small" @click="compress">{{ t('压缩') }}</el-button>
		</div>
		<div ref="editorEl" class="cl-editor-codemirror__editor" :style="{ height: parsePx(editorHeight) }" />
	</div>
</template>

<script lang="ts" setup>
defineOptions({
	name: 'cl-editor-codemirror'
});

import { computed, onBeforeUnmount, onMounted, shallowRef, watch, ref } from 'vue';
import { Compartment, EditorState, Extension } from '@codemirror/state';
import {
	EditorView,
	keymap,
	lineNumbers,
	highlightActiveLineGutter,
	highlightActiveLine,
	drawSelection,
	highlightSpecialChars
} from '@codemirror/view';
import { json, jsonParseLinter } from '@codemirror/lang-json';
import { oneDark } from '@codemirror/theme-one-dark';
import { linter, lintGutter } from '@codemirror/lint';
import { defaultKeymap, history, historyKeymap, indentWithTab } from '@codemirror/commands';
import { closeBrackets, closeBracketsKeymap } from '@codemirror/autocomplete';
import { foldGutter, indentUnit } from '@codemirror/language';
import { useDark } from '@vueuse/core';
import { parsePx } from '/@/cool/utils';
import { useI18n } from 'vue-i18n';
import { ElMessage } from 'element-plus';
import { elementPlusLightTheme } from '../utils/theme';

const props = defineProps({
	modelValue: String,
	height: {
		type: [String, Number],
		default: 300
	},
	disabled: Boolean,
	preview: Boolean
});

const emit = defineEmits(['update:modelValue', 'change']);

const { t } = useI18n();
const isDark = useDark();

const editorEl = ref<HTMLElement>();
const view = shallowRef<EditorView>();

const themeCompartment = new Compartment();
const readOnlyCompartment = new Compartment();

const TOOLBAR_HEIGHT = 32;

const editorHeight = computed(() => {
	if (props.preview) return props.height;
	const h = typeof props.height === 'number' ? props.height : parseInt(String(props.height), 10);
	if (isNaN(h)) return props.height;
	return Math.max(h - TOOLBAR_HEIGHT, 100);
});

function getExtensions(): Extension[] {
	return [
		highlightSpecialChars(),
		history(),
		drawSelection(),
		indentUnit.of('  '),
		json(),
		linter(jsonParseLinter()),
		lintGutter(),
		keymap.of([...closeBracketsKeymap, ...defaultKeymap, ...historyKeymap, indentWithTab]),
		closeBrackets(),
		foldGutter(),
		highlightActiveLineGutter(),
		highlightActiveLine(),
		lineNumbers(),
		themeCompartment.of(isDark.value ? oneDark : elementPlusLightTheme),
		readOnlyCompartment.of(EditorState.readOnly.of(props.disabled || props.preview)),
		EditorView.updateListener.of(update => {
			if (update.docChanged) {
				const val = update.state.doc.toString();
				emit('update:modelValue', val);
				emit('change', val);
			}
		})
	];
}

onMounted(() => {
	if (!editorEl.value) return;

	view.value = new EditorView({
		state: EditorState.create({
			doc: props.modelValue || '',
			extensions: getExtensions()
		}),
		parent: editorEl.value
	});
});

watch(isDark, dark => {
	if (!view.value) return;
	view.value.dispatch({
		effects: themeCompartment.reconfigure(dark ? oneDark : elementPlusLightTheme)
	});
});

watch([() => props.disabled, () => props.preview], ([disabled, preview]) => {
	if (!view.value) return;
	view.value.dispatch({
		effects: readOnlyCompartment.reconfigure(EditorState.readOnly.of(disabled || preview))
	});
});

watch(
	() => props.modelValue,
	newVal => {
		if (!view.value) return;
		const current = view.value.state.doc.toString();
		if (newVal !== current) {
			view.value.dispatch({
				changes: { from: 0, to: view.value.state.doc.length, insert: newVal || '' }
			});
		}
	}
);

function format() {
	if (!view.value) return;
	try {
		const raw = view.value.state.doc.toString();
		const parsed = JSON.parse(raw);
		const formatted = JSON.stringify(parsed, null, 2);
		view.value.dispatch({
			changes: { from: 0, to: view.value.state.doc.length, insert: formatted }
		});
	} catch {
		ElMessage.warning(t('JSON 格式不正确，无法格式化'));
	}
}

function compress() {
	if (!view.value) return;
	try {
		const raw = view.value.state.doc.toString();
		const parsed = JSON.parse(raw);
		const compressed = JSON.stringify(parsed);
		view.value.dispatch({
			changes: { from: 0, to: view.value.state.doc.length, insert: compressed }
		});
	} catch {
		ElMessage.warning(t('JSON 格式不正确，无法压缩'));
	}
}

function getValue(): string {
	return view.value?.state.doc.toString() || '';
}

function setValue(val: string) {
	if (!view.value) return;
	view.value.dispatch({
		changes: { from: 0, to: view.value.state.doc.length, insert: val }
	});
}

onBeforeUnmount(() => {
	view.value?.destroy();
});

defineExpose({ format, compress, formatCode: format, getValue, setValue });
</script>

<style lang="scss" scoped>
.cl-editor-codemirror {
	border: 1px solid var(--el-border-color);
	border-radius: var(--el-border-radius-base);
	overflow: hidden;
	transition: border-color 0.2s;

	&:focus-within {
		border-color: var(--el-color-primary);
	}

	&__toolbar {
		display: flex;
		align-items: center;
		gap: 4px;
		padding: 2px 8px;
		border-bottom: 1px solid var(--el-border-color-lighter);
		background: var(--el-fill-color-blank);
		height: 32px;
		box-sizing: border-box;
	}

	&__editor {
		:deep(.cm-editor) {
			height: 100%;
			font-size: 13px;
			font-family: 'Menlo', 'Monaco', 'Courier New', monospace;

			.cm-scroller {
				overflow: auto;
			}

			.cm-content {
				padding: 8px 0;
			}

			.cm-focused {
				outline: none;
			}

			.cm-gutters {
				border-right: 1px solid var(--el-border-color-lighter);
			}
		}
	}

	&.disabled,
	&.is-preview {
		.cl-editor-codemirror__editor {
			:deep(.cm-content) {
				cursor: default;
			}
			:deep(.cm-cursor) {
				display: none;
			}
		}
		background-color: var(--el-disabled-bg-color);
	}
}
</style>
