<template>
	<base-node
		:label="label"
		:selected="selected"
		:incomplete="incomplete"
		:is-child="isChild"
		:group-label="groupLabel"
		:has-target="true"
		:has-source="false"
		:node-height="nodeHeight"
		:custom-output-handles="outputHandles"
	/>
</template>

<script setup lang="ts">
import { computed } from 'vue';
import BaseNode from './base-node.vue';
import type { CustomOutputHandle } from './types';

const props = defineProps<{
	label: string;
	selected?: boolean;
	incomplete?: boolean;
	isChild?: boolean;
	groupLabel?: string;
	data?: any;
}>();

const cases = computed(() => props.data?.config?.cases || []);
const totalCount = computed(() => cases.value.length + 1);

const nodeHeight = computed(() => Math.max(56, totalCount.value * 28 + 28));

const outputHandles = computed<CustomOutputHandle[]>(() => {
	const handles: CustomOutputHandle[] = [];
	cases.value.forEach((c: any, i: number) => {
		const top = ((i + 1) * 100) / (totalCount.value + 1);
		handles.push({
			id: 'case_' + i,
			label: c.value || 'C' + (i + 1),
			color: '#e6a23c',
			topPercent: top,
			labelClass: 'handle-label--case',
			handleClass: 'handle-case'
		});
	});
	// 默认分支
	const defaultTop = (totalCount.value * 100) / (totalCount.value + 1);
	handles.push({
		id: 'default',
		label: '默认',
		color: '#909399',
		topPercent: defaultTop,
		labelClass: 'handle-label--default',
		handleClass: 'handle-default'
	});
	return handles;
});
</script>
