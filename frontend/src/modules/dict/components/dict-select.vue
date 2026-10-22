<script setup lang="ts">
// 字典单选（dict.mdc：useDict() → dict.get(type)，computed 保持响应性）。
import { computed } from 'vue';
import { useDict } from '/$/dict';

const props = defineProps<{
	dictType: string;
	modelValue?: string | number | null;
	placeholder?: string;
	clearable?: boolean;
}>();

const emit = defineEmits<{ (e: 'update:modelValue', value: string | number | null): void }>();

const { dict } = useDict();
const options = computed(() => dict.get(props.dictType).value ?? []);

function onChange(value: unknown) {
	emit('update:modelValue', (value ?? null) as string | number | null);
}
</script>

<template>
	<el-select
		:model-value="modelValue ?? undefined"
		:placeholder="placeholder"
		:clearable="clearable !== false"
		@update:model-value="onChange"
	>
		<el-option v-for="item in options" :key="item.value" :label="item.label" :value="item.value" />
	</el-select>
</template>
