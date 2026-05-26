<template>
	<BaseNode
		:label="label"
		:selected="selected"
		:icon="Files"
		node-class="node-batch_processor"
		:has-target="true"
		:has-source="true"
	/>
</template>

<script setup lang="ts">
import BaseNode from './base-node.vue';
import { Files } from '@element-plus/icons-vue';

defineProps<{
	label: string;
	selected?: boolean;
}>();
</script>
