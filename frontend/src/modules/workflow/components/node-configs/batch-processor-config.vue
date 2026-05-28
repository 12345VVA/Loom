<template>
	<el-form-item :label="$t('批处理列表变量名')" required>
		<el-input v-model="config.batchListVariable" placeholder="默认: batch_list_variable" />
	</el-form-item>
	<el-form-item :label="$t('单项变量名')">
		<el-input v-model="config.itemVariable" placeholder="默认: batch_item" />
	</el-form-item>
	<el-form-item :label="$t('并发上限')" required>
		<el-input-number v-model="config.concurrencyLimit" :min="1" :max="20" style="width: 100%" />
	</el-form-item>
	<el-form-item :label="$t('结果输出变量')" required>
		<el-input v-model="config.outputVariable" placeholder="默认: batch_results" />
	</el-form-item>
	<div class="auto-group-hint">
		<el-icon><InfoFilled /></el-icon>
		<span>批处理体容器已自动创建，将节点拖入容器即可加入批处理体。</span>
	</div>
</template>

<script setup lang="ts">
import { InfoFilled } from '@element-plus/icons-vue';

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

.auto-group-hint {
	display: flex;
	align-items: flex-start;
	gap: 6px;
	padding: 8px 10px;
	background: var(--el-fill-color-light);
	border-radius: 6px;
	border: 1px solid var(--el-border-color-lighter);
	font-size: 12px;
	color: var(--el-text-color-secondary);
	line-height: 1.5;

	.el-icon {
		margin-top: 2px;
		color: var(--el-color-info);
		flex-shrink: 0;
	}
}
</style>
