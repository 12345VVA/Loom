<template>
	<div class="response-format-editor">
		<div class="response-format-editor__head">
			<el-segmented v-model="mode" :options="modeOptions" />
			<el-tooltip placement="top" effect="dark">
				<template #content>
					<div class="response-format-editor__tip">
						{{
							$t(
								'OpenAI Compatible、DeepSeek、百炼、火山方舟、混元、千帆、智谱、MiniMax 等兼容适配器会透传 response_format；Claude、Gemini、Ollama 暂不做协议转换，可能由上游拒绝或忽略。'
							)
						}}
					</div>
				</template>
				<el-icon class="response-format-editor__tip-icon"><info-filled /></el-icon>
			</el-tooltip>
		</div>

		<template v-if="mode === 'json_schema'">
			<el-input v-model="schemaName" class="mt-2" placeholder="schema_name" />
			<el-input v-model="schemaDescription" class="mt-2" placeholder="description" />
			<el-switch
				v-model="schemaStrict"
				class="mt-2"
				active-text="strict"
			/>
			<cl-editor-codemirror v-model="schemaBody" class="mt-2" :height="300" />
			<div v-if="error" class="response-format-editor__error">{{ error }}</div>
		</template>
	</div>
</template>

<script lang="ts" setup>
defineOptions({
	name: 'ai-response-format-editor'
});

import { ref, watch } from 'vue';
import { useI18n } from 'vue-i18n';
import { InfoFilled } from '@element-plus/icons-vue';

const { t } = useI18n();

const props = defineProps<{
	modelValue?: string;
}>();

const emit = defineEmits<{
	(e: 'update:modelValue', v: string): void;
}>();

const modeOptions = [
	{ label: 'Text', value: 'text' },
	{ label: 'JSON Object', value: 'json_object' },
	{ label: 'JSON Schema', value: 'json_schema' }
];

const DEFAULT_SCHEMA_BODY =
	'{\n  "type": "object",\n  "properties": {},\n  "required": [],\n  "additionalProperties": false\n}';

const mode = ref<'text' | 'json_object' | 'json_schema'>('text');
const schemaName = ref('');
const schemaDescription = ref('');
const schemaStrict = ref(true);
const schemaBody = ref(DEFAULT_SCHEMA_BODY);
const error = ref('');

// 序列化失败时保留的最近合法值，保证表单值始终可提交
let lastValid = props.modelValue || '';

// 解析后端 responseFormat 字符串 → 内部状态（保持原 parseResponseFormat 契约）
function applyModelValue(value?: string) {
	if (!value) {
		mode.value = 'text';
		schemaName.value = '';
		schemaDescription.value = '';
		schemaStrict.value = true;
		schemaBody.value = DEFAULT_SCHEMA_BODY;
		return;
	}
	try {
		const data = JSON.parse(value);
		if (data?.type === 'json_object') {
			mode.value = 'json_object';
			return;
		}
		if (data?.type === 'json_schema') {
			const jsonSchema = data.json_schema || data.jsonSchema || {};
			mode.value = 'json_schema';
			schemaName.value = jsonSchema.name || '';
			schemaDescription.value = jsonSchema.description || '';
			schemaStrict.value = jsonSchema.strict !== false;
			schemaBody.value = JSON.stringify(jsonSchema.schema || {}, null, 2);
			return;
		}
		mode.value = 'text';
	} catch {
		mode.value = 'text';
	}
}

// 内部状态 → responseFormat 字符串（保持原 stringifyResponseFormat 契约）
function serialize(): string | null {
	if (mode.value === 'text') {
		return '';
	}
	if (mode.value === 'json_object') {
		return JSON.stringify({ type: 'json_object' });
	}
	if (!schemaName.value.trim()) {
		error.value = t('schema_name 不能为空');
		return null;
	}
	let schema: any;
	try {
		schema = JSON.parse(schemaBody.value || '{}');
	} catch {
		error.value = t('schema JSON 格式错误');
		return null;
	}
	return JSON.stringify({
		type: 'json_schema',
		json_schema: {
			name: schemaName.value.trim(),
			description: schemaDescription.value || undefined,
			schema,
			strict: schemaStrict.value !== false
		}
	});
}

// 回填：info 加载时重新解析；编辑触发的回写（值一致）不重 parse，防循环
watch(
	() => props.modelValue,
	value => {
		const next = value || '';
		if (next === lastValid) {
			return;
		}
		lastValid = next;
		applyModelValue(next);
	},
	{ immediate: true }
);

// 用户编辑内部状态时尝试序列化并上抛；失败时不覆盖表单值，仅展示错误
watch(
	[mode, schemaName, schemaDescription, schemaStrict, schemaBody],
	() => {
		const value = serialize();
		if (value === null) {
			return;
		}
		error.value = '';
		lastValid = value;
		emit('update:modelValue', value);
	}
);
</script>

<style lang="scss" scoped>
.response-format-editor {
	width: 100%;

	&__head {
		display: flex;
		align-items: center;
		gap: 8px;
	}

	&__tip {
		max-width: 260px;
		line-height: 1.5;
	}

	&__tip-icon {
		color: var(--el-text-color-placeholder);
		cursor: help;
		transition: color 0.3s;

		&:hover {
			color: var(--el-color-primary);
		}
	}

	&__error {
		margin-top: 4px;
		color: var(--el-color-danger);
		font-size: 12px;
	}

	.mt-2 {
		margin-top: 8px;
	}
}
</style>
