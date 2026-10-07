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
						<div v-if="scopeVars?.length" class="var-group">
							<div class="var-group-title">{{ $t(scopeTitle) }}</div>
							<div
								v-for="v in scopeVars"
								:key="v.key"
								class="var-item"
								@click="insert(v.refText)"
							>
								<span>{{ v.display }}</span>
								<small>{{ v.nodeLabel }}</small>
							</div>
						</div>
						<div v-if="!loopContextVars?.length && !scopeVars?.length" class="empty-hint">
							{{ $t('暂无可用变量') }}
						</div>
					</div>
				</el-popover>
			</template>
		</el-input>
	</div>
</template>

<script setup lang="ts">
import { computed, ref, inject } from 'vue';
import { Link } from '@element-plus/icons-vue';
import { UPSTREAM_OUTPUT_VARS_KEY, UPSTREAM_VARIABLES_KEY, LOOP_CONTEXT_VARS_KEY } from './constants';

defineOptions({
	name: 'cl-variable-input'
});

const props = withDefaults(
	defineProps<{
		modelValue: string;
		showVariableBtn?: boolean;
		/**
		 * 变量数据源口径（复审 P0-2）：按字段的执行器读取语义选择。
		 * - local：本节点 inputs 名（prompt 模板插值类字段——llm/end/image 模板经
		 *   node_inputs 渲染，本地名口径）；
		 * - global：全局上游变量（执行器经 _global_vars 读取的字段——switch 判断
		 *   变量 / transform 输入变量 / condition 表达式 / assignment 表达式）。
		 * 此前一刀切给本节点输入名，全局读取类字段选中的 input_1 在整图执行时
		 * 静默取 None（单节点测试因 mock 预填同名恰好通过）。
		 */
		scope?: 'local' | 'global';
	}>(),
	{
		showVariableBtn: true,
		scope: 'local'
	}
);

const emit = defineEmits(['update:modelValue']);

const upstreamOutputVars = inject(UPSTREAM_OUTPUT_VARS_KEY, ref([]));
const globalUpstreamVars = inject(UPSTREAM_VARIABLES_KEY, ref([]));
const loopContextVars = inject(LOOP_CONTEXT_VARS_KEY, ref([]));

const scopeVars = computed(() => (props.scope === 'global' ? globalUpstreamVars.value : upstreamOutputVars.value));
const scopeTitle = computed(() => (props.scope === 'global' ? '上游输出' : '本节点输入'));

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
