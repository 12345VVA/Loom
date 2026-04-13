<template>
	<span class="cl-date-text">{{ value }}</span>
</template>

<script lang="ts" setup>
defineOptions({
	name: 'cl-date-text'
});

import { computed } from 'vue';
import dayjs from 'dayjs';

const props = defineProps({
	modelValue: [String, Number],
	format: {
		type: String,
		default: 'YYYY-MM-DD HH:mm:ss'
	}
});

const value = computed(() => {
	return props.modelValue ? dayjs(props.modelValue).format(props.format) : '';
});
</script>
