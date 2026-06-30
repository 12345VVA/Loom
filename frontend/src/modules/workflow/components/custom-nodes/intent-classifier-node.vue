<template>
	<div
		class="custom-flow-node node-intent_classifier"
		:class="{ 'is-selected': selected, 'is-child': isChild, 'is-incomplete': incomplete }"
		:style="{ height: nodeHeight + 'px' }"
	>
		<handle type="target" :position="Position.Left" />
		<el-icon class="node-icon"><magic-stick /></el-icon>
		<span class="node-label">{{ label }}</span>
		<span v-if="isChild" class="child-badge">{{ groupLabel }}</span>
		<span v-if="incomplete" class="node-incomplete-dot" />
		<div class="output-handles">
			<div v-for="(intent, i) in intents" :key="intent.id ?? i" class="handle-group">
				<span
					class="handle-label handle-label--intent"
					:style="{ top: handleTop(Number(i)) }"
					>{{ intent.name || 'I' + (Number(i) + 1) }}</span
				>
				<handle
					:id="'intent_' + (intent.id ?? i)"
					type="source"
					:position="Position.Right"
					:style="{ top: handleTop(Number(i)) }"
				/>
			</div>
			<div class="handle-group">
				<span
					class="handle-label handle-label--default"
					:style="{ top: handleTop(intents.length) }"
					>默认</span
				>
				<handle
					id="default"
					type="source"
					:position="Position.Right"
					:style="{ top: handleTop(intents.length) }"
				/>
			</div>
		</div>
	</div>
</template>

<script setup lang="ts">
defineOptions({ name: 'workflow-node-intent-classifier' });
import { computed } from 'vue';
import { Handle, Position } from '@vue-flow/core';
import { MagicStick } from '@element-plus/icons-vue';

const props = defineProps<{
	label: string;
	selected?: boolean;
	incomplete?: boolean;
	isChild?: boolean;
	groupLabel?: string;
	data?: any;
}>();

const intents = computed(() => props.data?.config?.intents || []);
const totalCount = computed(() => intents.value.length + 1);

function handleTop(index: number): string {
	return `${((index + 1) * 100) / (totalCount.value + 1)}%`;
}

const nodeHeight = computed(() => Math.max(56, totalCount.value * 28 + 28));
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
	box-sizing: border-box;
	transition: all 0.2s ease-in-out;
	position: relative;

	&:hover {
		box-shadow: 0 6px 16px rgba(0, 0, 0, 0.08);
	}

	&.is-selected {
		border-color: var(--el-color-primary);
		box-shadow:
			0 0 0 2px rgba(64, 158, 255, 0.2),
			0 4px 12px rgba(64, 158, 255, 0.1);
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
		background-color: var(--wf-color-intent-classifier);
		border: 2px solid #ffffff;
		box-shadow: 0 2px 4px rgba(0, 0, 0, 0.1);
		border-radius: 50%;
		transition: background-color 0.2s;

		&:hover {
			transform: scale(1.3);
		}
	}
}

.node-intent_classifier {
	border-left: 4px solid var(--wf-color-intent-classifier);
	.node-icon {
		color: var(--wf-color-intent-classifier);
	}
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
	font-weight: 600;
	color: var(--wf-color-intent-classifier);
	transform: translateY(-50%);
	z-index: 2;
	user-select: none;
	max-width: 60px;
	overflow: hidden;
	text-overflow: ellipsis;
	white-space: nowrap;
}

.handle-label--intent {
	color: var(--wf-color-intent-classifier);
}

.handle-label--default {
	color: #909399;
	font-weight: 400;
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
