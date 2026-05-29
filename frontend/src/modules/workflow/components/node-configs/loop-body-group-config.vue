<template>
	<div class="loop-body-group-config">
		<el-form-item :label="$t('容器名称')">
			<el-input v-model="config.label" placeholder="循环体" />
		</el-form-item>
		<div class="group-hint">
			<el-icon><info-filled /></el-icon>
			<span>将节点拖入容器即可加入循环体，容器会自动扩展以适应内部节点。</span>
		</div>
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
.loop-body-group-config {
	.group-hint {
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
}
</style>
