<template>
	<div class="custom-flow-node" :class="[nodeClass, { 'is-selected': selected, 'is-child': isChild }]">
		<Handle v-if="hasTarget" type="target" :position="Position.Left" />
		<el-icon class="node-icon">
			<component :is="icon" />
		</el-icon>
		<span class="node-label">{{ label }}</span>
		<span v-if="isChild" class="child-badge">{{ groupLabel }}</span>
		<span v-if="incomplete" class="node-incomplete-dot" />
		<Handle v-if="hasSource" type="source" :position="Position.Right" />
	</div>
</template>

<script setup lang="ts">
import { Handle, Position } from '@vue-flow/core';

defineProps<{
	label: string;
	selected?: boolean;
	icon: any;
	nodeClass: string;
	hasTarget?: boolean;
	hasSource?: boolean;
	isChild?: boolean;
	groupLabel?: string;
	incomplete?: boolean;
}>();
</script>

<style lang="scss" scoped>
.custom-flow-node {
	display: flex;
	align-items: center;
	gap: 10px;
	padding: 10px 16px;
	background-color: #ffffff;
	border: 1px solid var(--el-border-color);
	border-radius: 8px;
	box-shadow: 0 4px 12px rgba(0, 0, 0, 0.05);
	font-size: 13px;
	font-weight: 500;
	color: var(--el-text-color-primary);
	min-width: 150px;
	height: 42px;
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
			background-color: #66b1ff;
		}
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

.node-start {
	border-left: 4px solid var(--el-color-success);
	.node-icon { color: var(--el-color-success); }
}
.node-llm {
	border-left: 4px solid var(--el-color-primary);
	.node-icon { color: var(--el-color-primary); }
}
.node-tool, .node-tool_executor {
	border-left: 4px solid #8a2be2;
	.node-icon { color: #8a2be2; }
}
.node-condition {
	border-left: 4px solid var(--el-color-warning);
	.node-icon { color: var(--el-color-warning); }
}
.node-switch {
	border-left: 4px solid #e6a23c;
	.node-icon { color: #e6a23c; }
}
.node-human_input {
	border-left: 4px solid var(--el-color-info);
	.node-icon { color: var(--el-color-info); }
}
.node-intent_classifier {
	border-left: 4px solid #20b2aa;
	.node-icon { color: #20b2aa; }
}
.node-loop_controller {
	border-left: 4px solid #d2691e;
	.node-icon { color: #d2691e; }
}
.node-batch_processor {
	border-left: 4px solid #00ced1;
	.node-icon { color: #00ced1; }
}
.node-image_generator {
	border-left: 4px solid #ff69b4;
	.node-icon { color: #ff69b4; }
}
.node-end {
	border-left: 4px solid var(--el-color-danger);
	.node-icon { color: var(--el-color-danger); }
}
</style>
