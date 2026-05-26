<template>
	<BaseNode
		:label="label"
		:selected="selected"
		:icon="Setting"
		node-class="node-tool"
		:has-target="true"
		:has-source="true"
	/>
</template>

<script setup lang="ts">
import BaseNode from './base-node.vue';
import { Setting } from '@element-plus/icons-vue';

defineProps<{
	label: string;
	selected?: boolean;
}>();
</script>
