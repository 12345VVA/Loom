<template>
	<el-form-item :label="$t('选择工具')" required>
		<el-select v-model="config.toolName" style="width: 100%">
			<el-option :label="$t('网页搜索 (Search)')" value="web_search" />
			<el-option :label="$t('文件读写 (FileSystem)')" value="file_system" />
			<el-option :label="$t('计算器 (Calculator)')" value="calculator" />
		</el-select>
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
