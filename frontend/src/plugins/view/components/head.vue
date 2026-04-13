<template>
	<div class="cl-view-head">
		<div class="cl-view-head__back" @click="router.back()">
			<cl-svg name="back" />
		</div>

		<span class="cl-view-head__title">{{ title }}</span>

		<div class="op">
			<slot name="op"></slot>
		</div>
	</div>
</template>

<script setup lang="ts">
defineOptions({
	name: 'cl-view-head'
});

import { computed } from 'vue';
import { useCool } from '/@/cool';

const props = defineProps({
	title: String,
	border: Boolean
});

const { route, router } = useCool();

// 标题
const title = computed(() => props.title || route.query.title);
</script>

<style lang="scss" scoped>
.cl-view-head {
	display: flex;
	align-items: center;
	margin-bottom: 10px;
	height: 30px;

	&__back {
		display: flex;
		align-items: center;
		justify-content: center;
		cursor: pointer;
		height: 30px;
		width: 30px;
		font-size: 18px;
		border-radius: 6px;
		margin-right: 10px;
		background-color: var(--el-fill-color-lighter);

		&:hover {
			background-color: var(--el-fill-color-light);
			color: var(--el-color-primary);
		}
	}

	&__title {
		font-size: 14px;
		line-height: 1;
		margin-right: auto;
	}
}
</style>
