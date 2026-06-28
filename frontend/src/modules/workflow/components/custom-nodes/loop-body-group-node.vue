<template>
	<div
		class="loop-body-group-node"
		:class="{ 'is-selected': selected, 'is-drag-over': dragOver }"
	>
		<!-- 标题栏 -->
		<div class="group-header">
			<el-icon class="group-icon"><refresh v-if="isLoop" /><files v-else /></el-icon>
			<span class="group-label">{{ label }}</span>
		</div>

		<!-- 空态引导 -->
		<div v-if="childCount === 0" class="group-empty-hint">
			<el-icon><plus /></el-icon>
			<span>拖入节点以构建{{ isLoop ? '循环' : '批处理' }}体</span>
			<span class="sub-hint">内部节点首尾相连即可，无需与容器边缘连线</span>
		</div>

		<!-- 激活态引导底栏 -->
		<div v-else class="group-active-hint">
			<el-icon><info-filled /></el-icon>
			<span>隐式路由：无内部输入边的节点为起点，无输出边的为终点</span>
		</div>

		<!-- 左侧 Handle（入口） -->
		<handle type="target" :position="Position.Left" class="group-handle group-handle-left" />
		<!-- 右侧 Handle（出口） -->
		<handle type="source" :position="Position.Right" class="group-handle group-handle-right" />

		<!-- 右下角 resize 手柄 -->
		<div class="resize-handle" @mousedown.stop.prevent="startResize" />
	</div>
</template>

<script setup lang="ts">
import { computed, ref, inject } from 'vue';
import { Handle, Position } from '@vue-flow/core';
import { Refresh, Files, Plus, InfoFilled } from '@element-plus/icons-vue';

const props = defineProps<{
	label: string;
	selected?: boolean;
	data?: any;
	id?: string;
}>();

const isLoop = computed(() => {
	const ctrl = props.data?.config?.controllerNodeId || '';
	return !ctrl.includes('batch');
});

// 子节点数量：从 inject 的 elements 中计算
const getElements: any = inject('getElements', () => []);
const childCount = computed(() => {
	const elements = getElements();
	if (!elements || !props.id) return 0;
	return elements.filter((el: any) => !('source' in el) && el.parentNode === props.id).length;
});

// 拖入高亮状态（由 editor.vue 通过 DOM class 控制）
const dragOver = ref(false);

// --- Resize 手柄逻辑 ---
function startResize(e: MouseEvent) {
	const nodeEl = (e.target as HTMLElement).closest('.vue-flow__node') as HTMLElement;
	if (!nodeEl) return;

	// 从 VueFlow 拿到节点实例对象，以便修改并持久化 style
	const nodeId = nodeEl.getAttribute('data-id');
	const elements = getElements();
	const nodeObj = elements.find((el: any) => el.id === nodeId);

	const startX = e.clientX;
	const startY = e.clientY;
	const startW = nodeEl.offsetWidth;
	const startH = nodeEl.offsetHeight;

	function onMouseMove(ev: MouseEvent) {
		const dx = ev.clientX - startX;
		const dy = ev.clientY - startY;
		const newW = Math.max(400, startW + dx);
		const newH = Math.max(250, startH + dy);
		nodeEl.style.width = newW + 'px';
		nodeEl.style.height = newH + 'px';
	}

	function onMouseUp() {
		document.removeEventListener('mousemove', onMouseMove);
		document.removeEventListener('mouseup', onMouseUp);

		// 尺寸调整结束时，写入 node 的 style 中以持久化保存
		if (nodeObj) {
			if (!nodeObj.style) nodeObj.style = {};
			nodeObj.style.width = nodeEl.style.width;
			nodeObj.style.height = nodeEl.style.height;
		}
	}

	document.addEventListener('mousemove', onMouseMove);
	document.addEventListener('mouseup', onMouseUp);
}
</script>

<style lang="scss" scoped>
.loop-body-group-node {
	min-width: 400px;
	min-height: 250px;
	height: 100%;
	border: 2px dashed var(--el-color-warning);
	border-radius: 12px;
	background: rgba(230, 162, 60, 0.04);
	position: relative;
	transition:
		border-color 0.2s,
		box-shadow 0.2s,
		background 0.2s;

	&.is-selected {
		border-color: var(--el-color-warning-dark-2);
		box-shadow: 0 0 0 2px rgba(230, 162, 60, 0.2);
	}

	&.is-drag-over {
		border-color: var(--el-color-success);
		background: rgba(103, 194, 58, 0.06);
		box-shadow: 0 0 0 3px rgba(103, 194, 58, 0.2);
	}

	.group-header {
		position: absolute;
		top: 0;
		left: 0;
		right: 0;
		display: flex;
		align-items: center;
		gap: 6px;
		padding: 4px 12px;
		background: rgba(230, 162, 60, 0.08);
		border-radius: 10px 10px 0 0;
		border-bottom: 1px dashed rgba(230, 162, 60, 0.2);
		user-select: none;
		z-index: 2;

		.group-icon {
			font-size: 13px;
			color: var(--el-color-warning);
		}

		.group-label {
			font-size: 12px;
			font-weight: 600;
			color: var(--el-color-warning);
		}
	}

	.group-empty-hint {
		position: absolute;
		top: 50%;
		left: 50%;
		transform: translate(-50%, -50%);
		display: flex;
		flex-direction: column;
		align-items: center;
		gap: 8px;
		color: var(--el-text-color-placeholder);
		font-size: 13px;
		user-select: none;
		pointer-events: none;
		white-space: nowrap;

		.el-icon {
			font-size: 24px;
			opacity: 0.4;
			margin-bottom: 4px;
		}

		span {
			opacity: 0.8;
			font-weight: 500;
		}

		.sub-hint {
			font-size: 11px;
			opacity: 0.5;
			font-weight: normal;
		}
	}

	.group-active-hint {
		position: absolute;
		bottom: 8px;
		left: 0;
		right: 0;
		display: flex;
		justify-content: center;
		align-items: center;
		gap: 4px;
		font-size: 11px;
		color: var(--el-text-color-secondary);
		opacity: 0.5;
		pointer-events: none;
		user-select: none;
	}

	.group-handle {
		width: 10px;
		height: 10px;
		background: var(--el-color-warning);
		border: 2px solid #fff;
		border-radius: 50%;
		z-index: 10;
	}

	.group-handle-left {
		left: -6px;
		top: 50%;
		transform: translateY(-50%);
	}

	.group-handle-right {
		right: -6px;
		top: 50%;
		transform: translateY(-50%);
	}

	.resize-handle {
		position: absolute;
		right: 0;
		bottom: 0;
		width: 16px;
		height: 16px;
		cursor: se-resize;
		z-index: 10;

		&::after {
			content: '';
			position: absolute;
			right: 4px;
			bottom: 4px;
			width: 8px;
			height: 8px;
			border-right: 2px solid rgba(230, 162, 60, 0.4);
			border-bottom: 2px solid rgba(230, 162, 60, 0.4);
			border-radius: 0 0 4px 0;
		}

		&:hover::after {
			border-color: var(--el-color-warning);
		}
	}
}
</style>
