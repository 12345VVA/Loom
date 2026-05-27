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
			<cl-json-tree-editor v-model="config.outputFields" mode="value" />
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
import ClJsonTreeEditor from '../cl-json-tree-editor.vue';

const props = defineProps<{
	modelValue: Record<string, any>;
}>();

const config = props.modelValue;

function buildJson(children: any[]): any {
	const obj: Record<string, any> = {};
	for (const child of children) {
		if (!child.name) continue;
		if (child.type === 'object') {
			obj[child.name] = buildJson(child.children || []);
		} else if (child.type === 'array') {
			obj[child.name] = buildArray(child.children || []);
		} else {
			obj[child.name] = child.value || '';
		}
	}
	return obj;
}

function buildArray(children: any[]): any[] {
	return (children || []).map(child => {
		if (child.type === 'object') {
			return buildJson(child.children || []);
		} else if (child.type === 'array') {
			return buildArray(child.children || []);
		} else {
			return child.value || '';
		}
	});
}

const endNodeJsonPreview = computed(() => {
	const fields = config.outputFields || [];
	if (fields.length === 0) return '';
	const obj = buildJson(fields);
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
