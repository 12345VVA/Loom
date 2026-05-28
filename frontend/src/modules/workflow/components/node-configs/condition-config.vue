<template>
	<el-form-item :label="$t('条件表达式')" required>
		<el-input v-model="config.expression" placeholder="例如: score > 80" />
		<div class="field-hint">
			{{ $t('如果求值结果为 True，走 T 端口；反之走 F 端口。') }}
		</div>
	</el-form-item>
	<div class="config-hint">
		<el-icon><InfoFilled /></el-icon>
		<span>从节点的 T (True) / F (False) 端口直接连线到目标节点。</span>
	</div>
</template>

<script setup lang="ts">
import { InfoFilled } from '@element-plus/icons-vue';

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

.config-hint {
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
