<template>
	<BaseNode
		:label="label"
		:selected="selected"
		:icon="VideoPlay"
		node-class="node-start"
		:has-source="true"
	/>
</template>

<script setup lang="ts">
import BaseNode from './base-node.vue';
import { VideoPlay } from '@element-plus/icons-vue';

defineProps<{
	label: string;
	selected?: boolean;
}>();
</script>
