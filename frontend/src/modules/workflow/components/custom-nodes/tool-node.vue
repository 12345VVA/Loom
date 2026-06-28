<template>
	<div class="tool-node-wrapper">
		<el-tooltip
			effect="dark"
			:content="$t('此节点类型已弃用，建议使用「工具执行器」节点')"
			placement="top"
		>
			<el-tag class="deprecated-tag" type="warning" size="small">{{ $t('已弃用') }}</el-tag>
		</el-tooltip>
		<base-node
			:label="label"
			:selected="selected"
			:has-target="true"
			:has-source="true"
			:is-child="isChild"
			:group-label="groupLabel"
			:incomplete="incomplete"
		/>
	</div>
</template>

<script setup lang="ts">
defineOptions({ name: 'workflow-node-tool' });
import BaseNode from './base-node.vue';
defineProps<{
	label: string;
	selected?: boolean;
	incomplete?: boolean;
	isChild?: boolean;
	groupLabel?: string;
	data?: any;
}>();
</script>

<style lang="scss" scoped>
.tool-node-wrapper {
	position: relative;

	.deprecated-tag {
		position: absolute;
		top: -10px;
		right: -8px;
		z-index: 5;
		font-size: 10px;
		pointer-events: auto;
	}
}
</style>
