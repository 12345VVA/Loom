<template>
	<path :d="path" fill="none" :stroke="edgeColor" :stroke-width="style?.strokeWidth || 2" :stroke-dasharray="isConditional ? '6 3' : undefined" class="edge-visible-path" />
	<g v-if="label" :transform="`translate(${labelX}, ${labelY})`">
		<rect
			:x="-labelHalfWidth - 6" y="-10" :width="labelWidth + 12" height="20"
			rx="4" :fill="labelBgColor" fill-opacity="0.95" :stroke="labelBorderColor" stroke-width="0.5"
			class="label-bg"
		/>
		<text
			text-anchor="middle" dominant-baseline="middle"
			font-size="11" :fill="textColor" font-weight="500"
		>{{ label }}</text>
	</g>
	<path :d="path" fill="none" stroke="transparent" stroke-width="12" class="edge-interaction" />
</template>

<script setup lang="ts">
import { computed } from 'vue';
import { getBezierPath, type Position } from '@vue-flow/core';

export interface LabelEdgeData {
	label?: string;
	labelColor?: string;
	condition?: string;
	[key: string]: any;
}

export interface LabelEdgeStyle {
	stroke?: string;
	strokeWidth?: number;
	[key: string]: any;
}

export interface LabelEdgeProps {
	id: string;
	sourceX: number;
	sourceY: number;
	targetX: number;
	targetY: number;
	sourcePosition: Position;
	targetPosition: Position;
	data?: LabelEdgeData;
	style?: LabelEdgeStyle;
	markerEnd?: string;
	label?: string;
	labelColor?: string;
	source?: string;
	target?: string;
	sourceHandle?: string;
	selected?: boolean;
}

const props = defineProps<LabelEdgeProps>();

// 模块级缓存的 canvas context，用于精确计算文字宽度
let _canvasCtx: CanvasRenderingContext2D | null = null;
function getCanvasContext() {
	if (!_canvasCtx) {
		const canvas = document.createElement('canvas');
		_canvasCtx = canvas.getContext('2d');
	}
	return _canvasCtx;
}

const path = computed(() => {
	const [edgePath] = getBezierPath({
		sourceX: props.sourceX,
		sourceY: props.sourceY,
		targetX: props.targetX,
		targetY: props.targetY,
		sourcePosition: props.sourcePosition,
		targetPosition: props.targetPosition,
	});
	return edgePath;
});

const labelX = computed(() => (props.sourceX + props.targetX) / 2);
const labelY = computed(() => (props.sourceY + props.targetY) / 2);

const label = computed(() => props.label || props.data?.label);
const textColor = computed(() => props.labelColor || props.data?.labelColor || '#666');

const isTrueBranch = computed(() => props.label === 'True' || props.data?.label === 'True');
const isFalseBranch = computed(() => props.label === 'False' || props.data?.label === 'False');

const isConditional = computed(() => isTrueBranch.value || isFalseBranch.value || !!props.data?.label);

const edgeColor = computed(() => {
	if (isTrueBranch.value) return '#67c23a';
	if (isFalseBranch.value) return '#f56c6c';
	return props.style?.stroke || '#409eff';
});

// 条件标签使用语义色背景
const labelBgColor = computed(() => {
	if (isTrueBranch.value) return 'rgba(103, 194, 58, 0.12)';
	if (isFalseBranch.value) return 'rgba(245, 108, 108, 0.12)';
	return 'white';
});

const labelBorderColor = computed(() => {
	if (isTrueBranch.value) return 'rgba(103, 194, 58, 0.3)';
	if (isFalseBranch.value) return 'rgba(245, 108, 108, 0.3)';
	return '#ddd';
});

// 精确计算标签宽度
const labelWidth = computed(() => {
	const text = label.value || '';
	if (!text) return 0;
	const ctx = getCanvasContext();
	if (ctx) {
		ctx.font = '500 11px sans-serif';
		return ctx.measureText(text).width;
	}
	// fallback: 近似计算
	return text.length * 8;
});
const labelHalfWidth = computed(() => labelWidth.value / 2);
</script>

<style scoped>
.edge-visible-path {
	transition: stroke 0.2s, stroke-width 0.2s;
}

.label-bg {
	filter: drop-shadow(0 1px 3px rgba(0, 0, 0, 0.08));
}

.edge-interaction {
	cursor: pointer;
}
</style>
