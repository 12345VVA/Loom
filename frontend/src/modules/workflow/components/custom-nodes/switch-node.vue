<template>
	<BaseNode
		:label="label"
		:selected="selected"
		:icon="Operation"
		node-class="node-switch"
		:has-target="true"
		:has-source="true"
	/>
</template>

<script setup lang="ts">
import BaseNode from './base-node.vue';
import { Operation } from '@element-plus/icons-vue';

defineProps<{
	label: string;
	selected?: boolean;
}>();
</script>
