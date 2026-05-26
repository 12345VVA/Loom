<template>
	<BaseNode
		:label="label"
		:selected="selected"
		:icon="CircleCheck"
		node-class="node-end"
		:has-target="true"
	/>
</template>

<script setup lang="ts">
import BaseNode from './base-node.vue';
import { CircleCheck } from '@element-plus/icons-vue';

defineProps<{
	label: string;
	selected?: boolean;
}>();
</script>
