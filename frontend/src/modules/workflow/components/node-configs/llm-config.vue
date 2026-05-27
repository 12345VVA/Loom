<template>
	<el-form-item :label="$t('AI 模型配置 (Profile)')" required>
		<el-select v-model="config.modelProfileCode" style="width: 100%">
			<el-option
				v-for="profile in profiles"
				:key="profile.code"
				:label="profile.name + ' (' + profile.code + ')'"
				:value="profile.code"
			/>
		</el-select>
	</el-form-item>

	<el-form-item :label="$t('Prompt 提示词模板')" required>
		<cl-editor-markdown v-model="config.promptTemplate" :height="320" simple placeholder="支持使用变量插值。例如：请写一篇关于 {input_query} 的文章" />
	</el-form-item>

	<el-form-item :label="$t('输出格式')">
		<el-select v-model="config.outputFormat" style="width: 100%">
			<el-option :label="$t('文本 (Text)')" value="text" />
			<el-option :label="$t('JSON (Schema 约束)')" value="json" />
			<el-option :label="$t('JSON (宽松模式)')" value="json_object" />
		</el-select>
		<div class="field-hint">
			<template v-if="config.outputFormat === 'json'">
				Schema 约束模式：根据下方字段定义自动生成 JSON Schema，模型在 API 层强制遵守结构输出。下游可用 {变量名.字段} 访问子字段。
			</template>
			<template v-else-if="config.outputFormat === 'json_object'">
				宽松模式：要求模型输出合法 JSON（API 层 json_object），但不限定 Schema。请在 Prompt 中自行描述所需的 JSON 结构。
			</template>
			<template v-else>
				普通文本输出。
			</template>
		</div>
	</el-form-item>

	<template v-if="config.outputFormat === 'json'">
		<el-form-item :label="$t('JSON 输出字段')">
			<div class="field-hint" style="margin-bottom: 8px;">定义期望 LLM 返回的 JSON 字段，系统自动生成 JSON Schema 约束模型输出，同时追加格式指令到提示词末尾。</div>
			<cl-json-tree-editor v-model="config.jsonFields" mode="schema" />
		</el-form-item>
	</template>

	<el-form-item :label="$t('输出变量写入')" required>
		<el-input v-model="config.outputVariable" placeholder="默认: output" />
	</el-form-item>
</template>

<script setup lang="ts">
import ClJsonTreeEditor from '../cl-json-tree-editor.vue';

const props = defineProps<{
	modelValue: Record<string, any>;
	profiles: any[];
}>();

const config = props.modelValue;
</script>

<style lang="scss" scoped>
.field-hint {
	font-size: 11px;
	color: var(--el-text-color-placeholder);
	margin-top: 4px;
	line-height: 1.4;
}
</style>
