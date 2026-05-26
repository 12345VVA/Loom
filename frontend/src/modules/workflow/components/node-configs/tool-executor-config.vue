<template>
	<el-form-item :label="$t('选择系统工具')" required>
		<el-select v-model="config.toolCode" style="width: 100%">
			<el-option :label="$t('网页搜索 (web_search)')" value="web_search" />
			<el-option :label="$t('本地文件系统读写 (file_system)')" value="file_system" />
		</el-select>
	</el-form-item>
	<el-form-item :label="$t('工具参数 JSON')" required>
		<el-input
			v-model="config.argumentsJson"
			type="textarea"
			:rows="5"
			placeholder='网页搜索参数：{"query": "variables.topic", "max_results": 3}&#10;文件读写参数：{"filename": "out.txt", "content": "variables.output"}'
		/>
		<div class="field-hint">支持以 "variables.变量名" 级联绑定上下文值。</div>
	</el-form-item>
	<el-form-item :label="$t('输出结果写入变量')" required>
		<el-input v-model="config.outputVariable" placeholder="默认: tool_result" />
	</el-form-item>
</template>

<script setup lang="ts">
const props = defineProps<{
	modelValue: Record<string, any>;
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
