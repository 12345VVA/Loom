<template>
	<div class="stats">
		<span v-for="item in items" :key="item.label" class="stat-chip">
			{{ item.label }}: {{ item.value }}
		</span>
	</div>
</template>

<script lang="ts" setup>
defineOptions({
	name: 'ai-stat-chips'
});

defineProps<{
	items: { label: string; value: string | number }[];
}>();
</script>

<style lang="scss" scoped>
.stats {
	display: flex;
	flex-wrap: wrap;
	gap: 8px;
	align-items: center;
}

.stat-chip {
	box-sizing: border-box;
	height: 36px;
	display: inline-flex;
	align-items: center;
	justify-content: center;
	padding: 0 12px;
	border: 1px solid var(--el-color-primary-light-5);
	border-radius: 6px;
	background: var(--el-fill-color-blank);
	color: var(--el-color-primary);
	font-size: 14px;
	line-height: 1;
	white-space: nowrap;
}
</style>
