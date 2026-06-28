<template>
	<div class="node-config-hint">
		<el-icon><info-filled /></el-icon>
		<div class="hint-content">
			<slot></slot>
		</div>
	</div>
</template>

<script setup lang="ts">
import { InfoFilled } from '@element-plus/icons-vue';
</script>

<style lang="scss" scoped>
.node-config-hint {
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
	
	.hint-content {
		flex: 1;
	}
}
</style>
