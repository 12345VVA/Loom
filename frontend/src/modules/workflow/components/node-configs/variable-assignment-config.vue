<template>
	<div class="variable-assignment-config">
		<el-form-item :label="$t('变量赋值列表')">
			<div v-for="(item, index) in config.assignments" :key="index" class="assignment-item">
				<div class="assignment-header">
					<span>{{ $t('变量') }} {{ Number(index) + 1 }}</span>
					<el-button type="danger" link icon="Delete" @click="removeAssignment(Number(index))" />
				</div>
				<el-form-item :label="$t('变量名')" label-width="80px">
					<el-input v-model="item.variable_name" placeholder="例如: base_url" />
				</el-form-item>
				<el-form-item :label="$t('类型')" label-width="80px">
					<el-select v-model="item.value_type" style="width: 100%">
						<el-option label="字符串 (String)" value="string" />
						<el-option label="数字 (Number)" value="number" />
						<el-option label="布尔 (Boolean)" value="boolean" />
						<el-option label="表达式 (Expression)" value="expression" />
					</el-select>
				</el-form-item>
				<el-form-item :label="$t('赋值内容')" label-width="80px">
					<el-input v-model="item.value" type="textarea" :rows="2" placeholder="输入值或表达式" />
				</el-form-item>
			</div>
			<el-button type="primary" plain icon="Plus" style="width: 100%; margin-top: 10px" @click="addAssignment">
				{{ $t('添加变量') }}
			</el-button>
		</el-form-item>
	</div>
</template>

<script setup lang="ts">
import { Delete, Plus } from '@element-plus/icons-vue';

const props = defineProps<{
	modelValue: Record<string, any>;
}>();

const config = props.modelValue;

if (!config.assignments) {
	config.assignments = [];
}

function addAssignment() {
	config.assignments.push({
		variable_name: '',
		value_type: 'string',
		value: ''
	});
}

function removeAssignment(index: number) {
	config.assignments.splice(index, 1);
}
</script>

<style scoped>
.assignment-item {
	border: 1px solid var(--el-border-color-light);
	border-radius: 4px;
	padding: 10px;
	margin-bottom: 10px;
	background-color: var(--el-fill-color-blank);
}
.assignment-header {
	display: flex;
	justify-content: space-between;
	align-items: center;
	margin-bottom: 10px;
	font-weight: bold;
	color: var(--el-text-color-regular);
}
</style>
