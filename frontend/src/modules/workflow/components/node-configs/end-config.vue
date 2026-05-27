<template>
	<el-form-item :label="$t('输出格式')">
		<el-select v-model="config.outputFormat" style="width: 100%">
			<el-option :label="$t('JSON 对象')" value="json" />
			<el-option :label="$t('纯文本')" value="text" />
		</el-select>
	</el-form-item>

	<!-- JSON 模式：结构化字段编辑器 -->
	<template v-if="config.outputFormat === 'json'">
		<el-form-item :label="$t('输出字段定义')">
			<div class="field-hint" style="margin-bottom: 8px;">定义工作流输出的 JSON 字段，值支持变量引用如 {变量名}。</div>
			<div
				v-for="(field, idx) in (config.outputFields || [])"
				:key="idx"
				style="display: flex; gap: 6px; margin-bottom: 6px; align-items: center;"
			>
				<el-input v-model="field.name" placeholder="字段名" style="width: 30%" />
				<el-input v-model="field.value" placeholder="值 (支持 {变量名})" style="flex: 1" />
				<el-button :icon="Delete" circle size="small" @click="removeOutputField(idx)" />
			</div>
			<el-button type="primary" link @click="addOutputField">
				<el-icon><Plus /></el-icon> {{ $t('添加字段') }}
			</el-button>
		</el-form-item>
		<el-form-item v-if="endNodeJsonPreview" :label="$t('JSON 预览')">
			<pre class="json-preview-block">{{ endNodeJsonPreview }}</pre>
		</el-form-item>
	</template>

	<!-- 文本模式 -->
	<template v-if="config.outputFormat === 'text'">
		<el-form-item :label="$t('输出模板')">
			<div class="field-hint" style="margin-bottom: 8px;">使用 {变量名} 引用上游变量，渲染结果作为纯文本输出。</div>
			<cl-editor-markdown v-model="config.outputTemplate" :height="260" placeholder="支持使用变量插值。例如：最终结果为 {LLM节点_output}" />
		</el-form-item>
	</template>
</template>

<script setup lang="ts">
import { computed } from 'vue';
import { Delete, Plus } from '@element-plus/icons-vue';

const props = defineProps<{
	modelValue: Record<string, any>;
}>();

const config = props.modelValue;

function addOutputField() {
	if (!config.outputFields) {
		config.outputFields = [];
	}
	config.outputFields.push({ name: '', value: '' });
}

function removeOutputField(index: number) {
	const fields = config.outputFields || [];
	fields.splice(index, 1);
}

const endNodeJsonPreview = computed(() => {
	const fields = config.outputFields || [];
	if (fields.length === 0) return '';
	const obj: Record<string, string> = {};
	for (const f of fields) {
		if (f.name) obj[f.name] = f.value || '';
	}
	return JSON.stringify(obj, null, 2);
});
</script>

<style lang="scss" scoped>
.field-hint {
	font-size: 11px;
	color: var(--el-text-color-placeholder);
	margin-top: 4px;
	line-height: 1.4;
}

.json-preview-block {
	background: #f5f7fa;
	border: 1px solid var(--el-border-color-lighter);
	border-radius: 4px;
	padding: 10px;
	font-size: 12px;
	max-height: 200px;
	overflow: auto;
	white-space: pre-wrap;
	margin: 0;
	color: var(--el-text-color-regular);
}
</style>
