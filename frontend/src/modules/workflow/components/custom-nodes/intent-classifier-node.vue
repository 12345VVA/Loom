<template>
	<base-node
		:label="label"
		:selected="selected"
		:incomplete="incomplete"
		:is-child="isChild"
		:group-label="groupLabel"
		:has-target="true"
		:has-source="false"
		:node-height="nodeHeight"
		:custom-output-handles="outputHandles"
	/>
</template>

<script setup lang="ts">
defineOptions({ name: 'workflow-node-intent-classifier' });
import { computed } from 'vue';
import BaseNode from './base-node.vue';
import type { CustomOutputHandle } from './types';

const props = defineProps<{
	label: string;
	selected?: boolean;
	incomplete?: boolean;
	isChild?: boolean;
	groupLabel?: string;
	data?: any;
}>();

const intents = computed(() => props.data?.config?.intents || []);
const totalCount = computed(() => intents.value.length + 1);

const nodeHeight = computed(() => Math.max(56, totalCount.value * 28 + 28));

// 多输出 Handle：每个意图一个分支 + 末尾默认分支（对齐 switch-node 写法）
// 🔒 数据兼容：Handle ID 必须保持 'intent_<id|i>' 与 'default'，否则现有 workflow 连线会断裂
const outputHandles = computed<CustomOutputHandle[]>(() => {
	const handles: CustomOutputHandle[] = [];
	intents.value.forEach((it: any, i: number) => {
		const top = ((i + 1) * 100) / (totalCount.value + 1);
		handles.push({
			id: 'intent_' + (it.id ?? i),
			label: it.name || 'I' + (i + 1),
			color: 'var(--wf-color-intent-classifier)',
			topPercent: top,
			labelClass: 'handle-label--intent',
			handleClass: 'handle-intent'
		});
	});
	// 默认分支
	const defaultTop = (totalCount.value * 100) / (totalCount.value + 1);
	handles.push({
		id: 'default',
		label: '默认',
		color: '#909399',
		topPercent: defaultTop,
		labelClass: 'handle-label--default',
		handleClass: 'handle-default'
	});
	return handles;
});
</script>
