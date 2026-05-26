<template>
	<el-form-item :label="$t('工作流输入变量')">
		<div class="field-hint" style="margin-bottom: 8px;">定义工作流启动时接收的变量名，下游节点可引用。</div>
		<div
			v-for="(varName, index) in (config.inputVariables || [])"
			:key="index"
			style="display: flex; gap: 6px; margin-bottom: 6px; align-items: center;"
		>
			<el-input
				v-model="config.inputVariables[index]"
				placeholder="变量名 (如 query)"
				size="small"
			/>
			<el-button
				type="danger"
				size="small"
				link
				:icon="Delete"
				@click="config.inputVariables.splice(index, 1)"
			/>
		</div>
		<el-button
			type="primary"
			size="small"
			plain
			:icon="Plus"
			@click="addVariable"
		>
			{{ $t('添加变量') }}
		</el-button>
	</el-form-item>
</template>

<script setup lang="ts">
import { Delete, Plus } from '@element-plus/icons-vue';

const props = defineProps<{
	modelValue: Record<string, any>;
}>();

const emit = defineEmits(['update:modelValue']);

const config = props.modelValue;

function addVariable() {
	if (!config.inputVariables) {
		config.inputVariables = [];
	}
	config.inputVariables.push('');
}
</script>
