<template>
	<base-node
		:label="label"
		:selected="selected"
		:incomplete="incomplete"
		:is-child="isChild"
		:group-label="groupLabel"
		:has-target="true"
		:has-source="false"
		:node-height="56"
		:custom-output-handles="outputHandles"
	/>
</template>

<script setup lang="ts">
import { computed } from 'vue';
import BaseNode from './base-node.vue';
import type { CustomOutputHandle } from './types';

defineProps<{
	label: string;
	selected?: boolean;
	incomplete?: boolean;
	isChild?: boolean;
	groupLabel?: string;
}>();

const outputHandles = computed(() => {
	const handles: CustomOutputHandle[] = [
		{
			id: 'true',
			label: 'T',
			color: '#67c23a',
			topPercent: 30,
			labelClass: 'handle-label--true',
			handleClass: 'handle-true'
		},
		{
			id: 'false',
			label: 'F',
			color: '#f56c6c',
			topPercent: 70,
			labelClass: 'handle-label--false',
			handleClass: 'handle-false'
		}
	];
	return handles;
});
</script>
