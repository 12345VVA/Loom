<template>
	<base-node
		:label="label"
		:selected="selected"
		:icon="Setting"
		node-class="node-tool_executor"
		:has-target="true"
		:has-source="true"
		:is-child="isChild"
		:group-label="groupLabel"
		:incomplete="incomplete"
	/>
</template>

<script setup lang="ts">
import BaseNode from './base-node.vue';
import { Setting } from '@element-plus/icons-vue';

defineProps<{
	label: string;
	selected?: boolean;
	incomplete?: boolean;
	isChild?: boolean;
	groupLabel?: string;
	data?: any;
}>();
</script>
