<template>
	<node-config-section :title="$t('基础配置')">
		<el-form-item :label="$t('批处理列表变量名')" required style="margin-bottom: 0;">
			<el-input v-model="config.batchListVariable" placeholder="默认: batch_list_variable" />
		</el-form-item>
		<el-form-item :label="$t('单项变量名')" style="margin-top: 18px; margin-bottom: 0;">
			<el-input v-model="config.itemVariable" placeholder="默认: batch_item" />
		</el-form-item>
		<el-form-item :label="$t('并发上限')" required style="margin-top: 18px; margin-bottom: 0;">
			<el-input-number v-model="config.concurrencyLimit" :min="1" :max="20" style="width: 100%" />
		</el-form-item>
		
		<node-config-hint style="margin-top: 16px;">
			<span>批处理体容器已自动创建，将节点拖入容器即可加入批处理体。</span>
		</node-config-hint>
	</node-config-section>
	<node-config-section :title="$t('输出')">
		<el-form-item :label="$t('输出变量写入')" required style="margin-bottom: 0;">
			<el-input v-model="config.outputVariable" placeholder="默认: batch_results" />
		</el-form-item>
	</node-config-section>
</template>

<script setup lang="ts">
import { computed } from 'vue';
import NodeConfigSection from './node-config-section.vue';
import NodeConfigHint from './node-config-hint.vue';

const props = defineProps<{
	modelValue: Record<string, any>;
	availableTargetNodes: any[];
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
