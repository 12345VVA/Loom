<template>
	<BaseNode
		:label="label"
		:selected="selected"
		:icon="MagicStick"
		node-class="node-intent_classifier"
		:has-target="true"
		:has-source="true"
	/>
</template>

<script setup lang="ts">
import BaseNode from './base-node.vue';
import { MagicStick } from '@element-plus/icons-vue';

defineProps<{
	label: string;
	selected?: boolean;
}>();
</script>
