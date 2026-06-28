<template>
	<div class="cl-variable-input">
		<el-input
			v-bind="$attrs"
			ref="inputRef"
			:model-value="modelValue"
			@update:model-value="emit('update:modelValue', $event)"
			@blur="saveCursor"
			@keyup="saveCursor"
			@mouseup="saveCursor"
		>
			<template #append v-if="showVariableBtn">
				<el-popover placement="bottom-end" :width="280" trigger="click">
					<template #reference>
						<el-button :icon="Link">{{ $t('变量') }}</el-button>
					</template>
					<div class="variable-list">
						<div v-if="loopContextVars?.length" class="var-group">
							<div class="var-group-title">{{ $t('循环上下文') }}</div>
							<div
								v-for="v in loopContextVars"
								:key="v.key"
								class="var-item"
								@click="insert(v.refText)"
							>
								<span>{{ v.display }}</span>
								<small>{{ v.nodeLabel }}</small>
							</div>
						</div>
						<div v-if="upstreamOutputVars?.length" class="var-group">
							<div class="var-group-title">{{ $t('上游输出') }}</div>
							<div
								v-for="v in upstreamOutputVars"
								:key="v.key"
								class="var-item"
								@click="insert(v.refText)"
							>
								<span>{{ v.display }}</span>
								<small>{{ v.nodeLabel }}</small>
							</div>
						</div>
						<div
							v-if="!loopContextVars?.length && !upstreamOutputVars?.length"
							class="empty-hint"
						>
							{{ $t('暂无可用变量') }}
						</div>
					</div>
				</el-popover>
			</template>
		</el-input>
	</div>
</template>

<script setup lang="ts">
import { ref, inject } from 'vue';
import { Link } from '@element-plus/icons-vue';
import type { Ref } from 'vue';
import { UPSTREAM_OUTPUT_VARS_KEY, LOOP_CONTEXT_VARS_KEY } from './constants';

defineOptions({
	name: 'cl-variable-input'
});

const props = withDefaults(
	defineProps<{
		modelValue: string;
		showVariableBtn?: boolean;
	}>(),
	{
		showVariableBtn: true
	}
);

const emit = defineEmits(['update:modelValue']);

const upstreamOutputVars = inject(UPSTREAM_OUTPUT_VARS_KEY, ref([]));
const loopContextVars = inject(LOOP_CONTEXT_VARS_KEY, ref([]));

const inputRef = ref();
const lastCursorPosition = ref<number | null>(null);

function saveCursor() {
	const el = inputRef.value?.$el?.querySelector('input, textarea') as HTMLInputElement | HTMLTextAreaElement;
	if (el && typeof el.selectionStart === 'number') {
		lastCursorPosition.value = el.selectionStart;
	}
}

function insert(refText: string) {
	const el = inputRef.value?.$el?.querySelector('input, textarea') as
		| HTMLInputElement
		| HTMLTextAreaElement;
	
	// 如果由于失焦没拿到 selectionStart，退回使用最近保存的光标位置，否则放到末尾
	let start = props.modelValue?.length || 0;
	if (el && typeof el.selectionStart === 'number' && document.activeElement === el) {
		start = el.selectionStart;
	} else if (lastCursorPosition.value !== null) {
		start = lastCursorPosition.value;
	}

	const val = props.modelValue || '';
	const newVal = val.slice(0, start) + refText + val.slice(start);
	emit('update:modelValue', newVal);

	const newCursorPos = start + refText.length;
	lastCursorPosition.value = newCursorPos;

	setTimeout(() => {
		const newEl = inputRef.value?.$el?.querySelector('input, textarea') as
			| HTMLInputElement
			| HTMLTextAreaElement;
		if (newEl) {
			newEl.focus();
			newEl.setSelectionRange(newCursorPos, newCursorPos);
		}
	}, 0);
}
</script>

<style scoped lang="scss">
@use '/@/modules/workflow/components/variable-list.scss';
</style>
