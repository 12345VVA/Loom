<template>
	<div :ref="setRefs('editor')" class="cl-editor-wang" :class="{ disabled }">
		<!-- 工具栏 -->
		<toolbar v-if="!preview" :editor="Editor" :mode="mode" />

		<!-- 编辑框 -->
		<editor-input
			v-model="value"
			:default-config="editorConfig"
			:mode="mode"
			:style="{
				height: parsePx(height)
			}"
			@on-created="onCreated"
			@on-focus="onFocus"
			@on-blur="onBlur"
			@on-change="onChange"
		/>

		<!-- 直接上传 - 视频 -->
		<div class="upload-inner">
			<cl-upload :ref="setRefs('video')" type="file" accept="video/*" @success="onFileConfirm" />
		</div>

		<!-- 直接上传 - 图片 -->
		<div class="upload-inner">
			<cl-upload :ref="setRefs('image')" accept="image/*" @success="onFileConfirm" />
		</div>
	</div>
</template>

<script lang="ts" setup>
defineOptions({
	name: 'cl-editor-wang'
});

import { onBeforeUnmount, ref, shallowRef, watch, type PropType } from 'vue';
import { Editor as EditorInput, Toolbar } from '@wangeditor/editor-for-vue';
import { type IEditorConfig } from '@wangeditor/editor';
import { useCool } from '/@/cool';
import { parsePx } from '/@/cool/utils';
import { isArray } from 'lodash-es';
import '@wangeditor/editor/dist/css/style.css';
import { useI18n } from 'vue-i18n';

const props = defineProps({
	modelValue: String,
	// 模式
	mode: {
		type: String as PropType<'default' | 'simple'>,
		default: 'default'
	},
	// 高度
	height: {
		type: [String, Number],
		default: 500
	},
	// 禁用
	disabled: Boolean,
	// 是否预览模式
	preview: Boolean,
	// 兼容旧参数，前端已不再依赖文件空间
	isSpace: {
		type: Boolean,
		default: false
	}
});

const emit = defineEmits(['update:modelValue', 'change', 'focus', 'blur']);

const { refs, setRefs } = useCool();
const { t } = useI18n();

// 编辑器
const Editor = shallowRef();

// 内容
const value = ref();

watch(
	() => props.modelValue,
	val => {
		value.value = val || '';
	},
	{
		immediate: true
	}
);

// 临时
const temp: { insertFn: ((url: string) => void) | null } = {
	insertFn: null
};

// 配置
const editorConfig: Partial<IEditorConfig> = {
	placeholder: t('请输入'),
	MENU_CONF: {
		uploadImage: {},
		uploadVideo: {
			customBrowseAndUpload(fn: any) {
				temp.insertFn = fn;
				refs.video.open();
			}
		}
	}
};

// 直接上传
editorConfig.MENU_CONF!.uploadImage.customUpload = (file: File, fn: any) => {
	temp.insertFn = fn;
	refs.image.upload(file);
};

// 创建后
function onCreated(editor: any) {
	Editor.value = editor;
	onDisabled();
}

// 聚焦
function onFocus(editor: any) {
	emit('focus', editor);
}

// 失焦
function onBlur(editor: any) {
	emit('blur', editor);
}

// 值改变
function onChange() {
	if (value.value == '<p><br></p>') {
		value.value = '';
	}

	emit('update:modelValue', value.value);
	emit('change', value.value);
}

// 文件选择
function onFileConfirm(files: any[]) {
	if (!isArray(files)) {
		files = [files];
	}

	if (files.length > 0) {
		files.forEach(file => {
			if (temp.insertFn) {
				temp.insertFn(file.url);
			}
		});
	}
}

// 禁用
function onDisabled() {
	if (props.disabled || props.preview) {
		Editor.value?.disable();
	} else {
		Editor.value?.enable();
	}
}

// 监听
watch(() => [props.disabled, props.preview], onDisabled);

// 销毁
onBeforeUnmount(() => {
	const editor = Editor.value;
	if (editor == null) return;
	editor.destroy();
});
</script>

<style lang="scss" scoped>
.cl-editor-wang {
	border: 1px solid var(--el-border-color);
	box-sizing: border-box;
	line-height: normal;

	:deep(.w-e-toolbar) {
		border-bottom: 1px solid var(--el-border-color);
	}

	:deep(input) {
		font-size: 12px;
	}

	:deep(button) {
		font-size: 12px;

		&::before {
			font-size: 12px;
		}
	}

	.upload-inner {
		visibility: hidden;
		position: absolute;
		left: 0;
		top: 0;
	}

	&.disabled {
		:deep(.w-e-text-container) {
			background-color: var(--el-disabled-bg-color);
		}
	}

	&.w-e-full-screen-container {
		z-index: 999;
	}
}
</style>
