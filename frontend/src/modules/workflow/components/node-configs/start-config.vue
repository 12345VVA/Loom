<template>
	<node-config-section :title="$t('全局输入')">
		<el-form-item :label="$t('工作流输入变量')" style="margin-bottom: 0">
			<div class="field-hint" style="margin-bottom: 8px">
				定义工作流启动时接收的变量名，下游节点可引用。
			</div>
			<div
				v-for="(varName, index) in config.inputVariables || []"
				:key="index"
				style="display: flex; gap: 6px; margin-bottom: 6px; align-items: flex-start"
			>
				<div style="flex: 1">
					<el-input
						v-model="config.inputVariables[index]"
						:class="{ 'is-error': getVarError(index) }"
						placeholder="变量名 (如 query)"
						size="small"
						@blur="validateVar(index)"
					/>
					<div v-if="getVarError(index)" class="var-error-tip">
						{{ getVarError(index) }}
					</div>
				</div>
				<el-button
					type="danger"
					size="small"
					link
					:icon="Delete"
					@click="removeVariable(index)"
				/>
			</div>
			<el-button type="primary" size="small" plain :icon="Plus" @click="addVariable">
				{{ $t('添加变量') }}
			</el-button>
		</el-form-item>
	</node-config-section>
</template>

<script setup lang="ts">
import { reactive } from 'vue';
import { Delete, Plus } from '@element-plus/icons-vue';
import NodeConfigSection from './node-config-section.vue';

const props = defineProps<{
	modelValue: Record<string, any>;
}>();

const emit = defineEmits(['update:modelValue']);

const config = props.modelValue;

// 变量名校验错误状态
const varErrors = reactive<Record<number, string>>({});

const VALID_NAME_REGEX = /^[a-zA-Z_][a-zA-Z0-9_]*$/;

function validateVar(index: number) {
	const name = (config.inputVariables?.[index] || '').trim();
	delete varErrors[index];

	if (!name) return; // 空值不校验（用户可能正在编辑）

	if (!VALID_NAME_REGEX.test(name)) {
		varErrors[index] = '变量名仅支持英文字母、数字和下划线，且不能以数字开头';
		return;
	}

	// 去重校验
	const list = config.inputVariables || [];
	const duplicateIndex = list.findIndex(
		(v: string, i: number) => i !== index && v.trim() === name
	);
	if (duplicateIndex !== -1) {
		varErrors[index] = `变量名与第 ${duplicateIndex + 1} 个重复`;
	}
}

function getVarError(index: number): string {
	return varErrors[index] || '';
}

function addVariable() {
	if (!config.inputVariables) {
		config.inputVariables = [];
	}
	config.inputVariables.push('');
}

function removeVariable(index: number) {
	config.inputVariables.splice(index, 1);
	delete varErrors[index];
	// 重新校验剩余变量（去重索引可能变化）
	Object.keys(varErrors).forEach(k => {
		const i = Number(k);
		if (i >= config.inputVariables.length) {
			delete varErrors[i];
		} else {
			validateVar(i);
		}
	});
}
</script>

<style scoped>
.var-error-tip {
	font-size: 11px;
	color: var(--el-color-danger);
	line-height: 1.4;
	margin-top: 2px;
}
</style>
