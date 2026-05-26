<template>
	<el-form-item :label="$t('向审批人展示的确认话术')">
		<el-input v-model="config.message" placeholder="您是否赞成该输出？" />
	</el-form-item>
	<el-form-item :label="$t('审批结果写入变量')" required>
		<el-input v-model="config.outputVariable" placeholder="默认: approval_status" />
	</el-form-item>
</template>

<script setup lang="ts">
const props = defineProps<{
	modelValue: Record<string, any>;
}>();

const config = props.modelValue;
</script>
