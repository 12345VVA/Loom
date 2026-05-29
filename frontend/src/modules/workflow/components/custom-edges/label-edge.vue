<template>
	<path :d="path" fill="none" :stroke="edgeColor" :stroke-width="style?.strokeWidth || 2" />
	<g v-if="label" :transform="`translate(${labelX}, ${labelY})`">
		<rect
			:x="-labelHalfWidth - 4" y="-10" :width="labelWidth + 8" height="20"
			rx="4" fill="white" fill-opacity="0.92" stroke="#ddd" stroke-width="0.5" />
		<text
			text-anchor="middle" dominant-baseline="middle"
			font-size="11" :fill="textColor">{{ label }}</text>
	</g>
	<path :d="path" fill="none" stroke="transparent" stroke-width="12" class="edge-interaction" />
</template>

<script setup lang="ts">
import { computed } from 'vue';
import { getBezierPath } from '@vue-flow/core';

const props = defineProps<{
	id: string;
	sourceX: number;
	sourceY: number;
	targetX: number;
	targetY: number;
	sourcePosition: any;
	targetPosition: any;
	data?: any;
	style?: any;
	markerEnd?: string;
	label?: string;
	labelColor?: string;
	source?: string;
	target?: string;
	sourceHandle?: string;
}>();

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

const edgeColor = computed(() => {
	if (props.label === 'True' || props.data?.label === 'True') return '#67c23a';
	if (props.label === 'False' || props.data?.label === 'False') return '#f56c6c';
	return props.style?.stroke || '#409eff';
});

const labelWidth = computed(() => {
	const text = label.value || '';
	return text.length * 7 + 4;
});
const labelHalfWidth = computed(() => labelWidth.value / 2);
</script>

<style scoped>
.edge-interaction {
	cursor: pointer;
}
</style>
