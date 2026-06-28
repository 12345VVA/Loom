<template>
	<node-config-section :title="$t('条件配置')">
		<el-form-item :label="$t('条件表达式')" required style="margin-bottom: 0;">
		<cl-variable-input v-model="config.expression" placeholder="例如: score > 80" @blur="validateExpression" />
		<div v-if="exprError" class="var-error-tip">{{ exprError }}</div>
		<div class="field-hint">
			{{ $t('如果求值结果为 True，走 T 端口；反之走 F 端口。') }}
		</div>
		</el-form-item>
		<node-config-hint style="margin-top: 8px;">
			<span>从节点的 T (True) / F (False) 端口直接连线到目标节点。</span>
		</node-config-hint>
	</node-config-section>
</template>

<script setup lang="ts">
import { ref } from 'vue';
import NodeConfigHint from './node-config-hint.vue';
import NodeConfigSection from './node-config-section.vue';
import ClVariableInput from '../cl-variable-input.vue';

const props = defineProps<{
	modelValue: Record<string, any>;
}>();

const config = props.modelValue;

const exprError = ref('');

function validateExpression() {
	const expr = (config.expression || '').trim();
	exprError.value = '';

	if (!expr) return;

	// 检查括号是否匹配
	let depth = 0;
	for (const ch of expr) {
		if (ch === '(') depth++;
		if (ch === ')') depth--;
		if (depth < 0) {
			exprError.value = '括号不匹配：多余的右括号';
			return;
		}
	}
	if (depth > 0) {
		exprError.value = '括号不匹配：缺少右括号';
		return;
	}

	// 检查 variables. 引用是否完整（variables. 后缺少变量名）
	const varPattern = /variables\.\s*(\b|$)/g;
	if (varPattern.test(expr)) {
		exprError.value = '变量引用不完整：variables. 后缺少变量名';
		return;
	}
}
</script>

<style lang="scss" scoped>
.field-hint {
	font-size: 11px;
	color: var(--el-text-color-placeholder);
	margin-top: 4px;
	line-height: 1.4;
}

.var-error-tip {
	font-size: 11px;
	color: var(--el-color-danger);
	margin-top: 4px;
	line-height: 1.4;
}
</style>
