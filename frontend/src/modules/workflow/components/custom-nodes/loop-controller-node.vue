<template>
	<BaseNode
		:label="label"
		:selected="selected"
		:icon="Refresh"
		node-class="node-loop_controller"
		:has-target="true"
		:has-source="true"
	/>
</template>

<script setup lang="ts">
import BaseNode from './base-node.vue';
import { Refresh } from '@element-plus/icons-vue';

defineProps<{
	label: string;
	selected?: boolean;
}>();
</script>
