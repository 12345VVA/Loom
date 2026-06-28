<template>
	<base-node
		:label="label"
		:selected="selected"
		:has-target="true"
		:is-child="isChild"
		:group-label="groupLabel"
		:incomplete="incomplete"
	/>
</template>

<script setup lang="ts">
defineOptions({ name: 'workflow-node-end' });
import BaseNode from './base-node.vue';
defineProps<{
	label: string;
	selected?: boolean;
	incomplete?: boolean;
	isChild?: boolean;
	groupLabel?: string;
	data?: any;
}>();
</script>
