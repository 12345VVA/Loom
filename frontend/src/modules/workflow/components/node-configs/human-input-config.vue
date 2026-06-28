<template>
	<node-config-section :title="$t('基础配置')">
		<el-form-item :label="$t('向审批人展示的确认话术')" style="margin-bottom: 0;">
		<el-input v-model="config.message" placeholder="您是否赞成该输出？" />
		</el-form-item>
	</node-config-section>
	<node-config-section :title="$t('输出')">
		<el-form-item :label="$t('输出变量写入')" required style="margin-bottom: 0;">
			<el-input v-model="config.outputVariable" placeholder="默认: approval_status" />
		</el-form-item>
	</node-config-section>
</template>

<script setup lang="ts">
import NodeConfigSection from './node-config-section.vue';

const props = defineProps<{
	modelValue: Record<string, any>;
}>();

const config = props.modelValue;
</script>
