<template>
	<BaseNode
		:label="label"
		:selected="selected"
		:icon="UserFilled"
		node-class="node-human_input"
		:has-target="true"
		:has-source="true"
	/>
</template>

<script setup lang="ts">
import BaseNode from './base-node.vue';
import { UserFilled } from '@element-plus/icons-vue';

defineProps<{
	label: string;
	selected?: boolean;
}>();
</script>
