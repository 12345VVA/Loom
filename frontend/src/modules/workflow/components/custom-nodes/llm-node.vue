<template>
	<BaseNode
		:label="label"
		:selected="selected"
		:icon="Cpu"
		node-class="node-llm"
		:has-target="true"
		:has-source="true"
	/>
</template>

<script setup lang="ts">
import BaseNode from './base-node.vue';
import { Cpu } from '@element-plus/icons-vue';

defineProps<{
	label: string;
	selected?: boolean;
}>();
</script>
