<template>
	<el-form-item :label="$t('循环数组变量名')" required>
		<el-input v-model="config.listVariable" placeholder="默认: list_variable" />
		<div class="field-hint">当前版本固化读取状态中的 list_variable。</div>
	</el-form-item>
	<el-form-item :label="$t('单项变量名')" required>
		<el-input v-model="config.itemVariable" placeholder="默认: loop_item" />
	</el-form-item>
	<el-form-item :label="$t('结果输出变量')" required>
		<el-input v-model="config.outputVariable" placeholder="默认: loop_results" />
	</el-form-item>
	<div class="auto-group-hint">
		<el-icon><info-filled /></el-icon>
		<span>循环体容器已自动创建，将节点拖入容器即可加入循环体。</span>
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
