<template>
	<BaseNode
		:label="label"
		:selected="selected"
		:icon="UserFilled"
		node-class="node-human_input"
		:has-target="true"
		:has-source="true"
		:is-child="isChild"
		:group-label="groupLabel"
		:incomplete="incomplete"
	/>
</template>

<script setup lang="ts">
import BaseNode from './base-node.vue';
import { UserFilled } from '@element-plus/icons-vue';

defineProps<{
	label: string;
	selected?: boolean;
	incomplete?: boolean;
	isChild?: boolean;
	groupLabel?: string;
	data?: any;
}>();
</script>
