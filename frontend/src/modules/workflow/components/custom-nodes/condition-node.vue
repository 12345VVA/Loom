<template>
	<div class="custom-flow-node node-condition" :class="{ 'is-selected': selected, 'is-child': isChild, 'is-incomplete': incomplete }">
		<handle type="target" :position="Position.Left" />
		<el-icon class="node-icon"><operation /></el-icon>
		<span class="node-label">{{ label }}</span>
		<span v-if="isChild" class="child-badge">{{ groupLabel }}</span>
		<span v-if="incomplete" class="node-incomplete-dot" />
		<div class="output-handles">
			<div class="handle-group">
				<span class="handle-label handle-label--true">T</span>
				<handle
				id="true" type="source" :position="Position.Right"
					:style="{ top: '30%' }" class="handle-true" />
			</div>
			<div class="handle-group">
				<span class="handle-label handle-label--false">F</span>
				<handle
				id="false" type="source" :position="Position.Right"
					:style="{ top: '70%' }" class="handle-false" />
			</div>
		</div>
	</div>
</template>

<script setup lang="ts">
import { Handle, Position } from '@vue-flow/core';
import { Operation } from '@element-plus/icons-vue';

defineProps<{
	label: string;
	selected?: boolean;
	incomplete?: boolean;
	isChild?: boolean;
	groupLabel?: string;
}>();
</script>

<style lang="scss" scoped>
.custom-flow-node {
	display: flex;
	align-items: center;
	gap: 10px;
	padding: 10px 28px 10px 16px;
	background-color: #ffffff;
	border: 1px solid var(--el-border-color);
	border-radius: 8px;
	box-shadow: 0 4px 12px rgba(0, 0, 0, 0.05);
	font-size: 13px;
	font-weight: 500;
	color: var(--el-text-color-primary);
	min-width: 150px;
	height: 56px;
	box-sizing: border-box;
	transition: all 0.2s ease-in-out;
	position: relative;

	&:hover {
		box-shadow: 0 6px 16px rgba(0, 0, 0, 0.08);
	}

	&.is-selected {
		border-color: var(--el-color-primary);
		box-shadow: 0 0 0 2px rgba(64, 158, 255, 0.2), 0 4px 12px rgba(64, 158, 255, 0.1);
	}

	&.is-child {
		border-style: dashed;
		border-width: 1.5px;
	}

	.node-icon {
		font-size: 16px;
		display: flex;
		align-items: center;
		justify-content: center;
	}

	.node-label {
		flex: 1;
		white-space: nowrap;
		overflow: hidden;
		text-overflow: ellipsis;
	}

	:deep(.vue-flow__handle) {
		width: 8px;
		height: 8px;
		background-color: #409eff;
		border: 2px solid #ffffff;
		box-shadow: 0 2px 4px rgba(0, 0, 0, 0.1);
		border-radius: 50%;
		transition: background-color 0.2s;

		&:hover {
			transform: scale(1.3);
		}
	}
}

.node-condition {
	border-left: 4px solid var(--el-color-warning);
	.node-icon { color: var(--el-color-warning); }
}

.output-handles {
	position: absolute;
	right: 0;
	top: 0;
	bottom: 0;
	width: 12px;
}

.handle-group {
	display: flex;
	align-items: center;
}

.handle-label {
	position: absolute;
	right: 16px;
	font-size: 10px;
	font-weight: 700;
	z-index: 2;
	user-select: none;
}

.handle-label--true {
	color: #67c23a;
	top: 30%;
	transform: translateY(-50%);
}

.handle-label--false {
	color: #f56c6c;
	top: 70%;
	transform: translateY(-50%);
}

.handle-true {
	:deep(.vue-flow__handle) {
		background-color: #67c23a !important;
	}
}

.handle-false {
	:deep(.vue-flow__handle) {
		background-color: #f56c6c !important;
	}
}

.child-badge {
	position: absolute;
	top: -8px;
	right: -4px;
	font-size: 10px;
	padding: 1px 6px;
	background: rgba(230, 162, 60, 0.15);
	color: var(--el-color-warning);
	border-radius: 4px;
	white-space: nowrap;
}

.node-incomplete-dot {
	position: absolute;
	top: -3px;
	left: 18px;
	width: 8px;
	height: 8px;
	background: var(--el-color-danger);
	border-radius: 50%;
	border: 2px solid #fff;
}
</style>
