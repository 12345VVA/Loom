<template>
	<base-node
		:label="label"
		:selected="selected"
		:icon="Picture"
		node-class="node-image_generator"
		:has-target="true"
		:has-source="true"
		:is-child="isChild"
		:group-label="groupLabel"
		:incomplete="incomplete"
	/>
</template>

<script setup lang="ts">
import BaseNode from './base-node.vue';
import { Picture } from '@element-plus/icons-vue';

defineProps<{
	label: string;
	selected?: boolean;
	incomplete?: boolean;
	isChild?: boolean;
	groupLabel?: string;
	data?: any;
}>();
</script>
