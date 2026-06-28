<template>
	<node-config-section :title="$t('变量赋值')">
		<template #actions>
			<el-button type="primary" link size="small" :icon="Plus" @click.stop="addAssignment">{{
				$t('添加')
			}}</el-button>
		</template>
		<div v-for="(item, index) in config.assignments" :key="index" class="assignment-item">
			<div class="assignment-header">
				<span>{{ $t('变量') }} {{ Number(index) + 1 }}</span>
				<el-button
					type="danger"
					link
					:icon="Delete"
					@click="removeAssignment(Number(index))"
				/>
			</div>
			<el-form-item :label="$t('变量名')" class="assignment-field">
				<el-input v-model="item.variable_name" placeholder="例如: base_url" />
			</el-form-item>
			<el-form-item :label="$t('类型')" class="assignment-field">
				<el-select v-model="item.value_type" style="width: 100%">
					<el-option label="字符串 (String)" value="string" />
					<el-option label="数字 (Number)" value="number" />
					<el-option label="布尔 (Boolean)" value="boolean" />
					<el-option label="表达式 (Expression)" value="expression" />
				</el-select>
			</el-form-item>
			<el-form-item :label="$t('赋值内容')" class="assignment-field">
				<cl-variable-input
					v-model="item.value"
					type="textarea"
					:rows="2"
					:placeholder="item.value_type === 'expression' ? '输入表达式' : '输入值'"
					:show-variable-btn="item.value_type === 'expression'"
				/>
			</el-form-item>
		</div>
		<div v-if="!config.assignments?.length" class="empty-hint" @click="addAssignment">
			<el-icon class="empty-icon"><plus /></el-icon>
			<span>{{ $t('暂无赋值变量，点击添加') }}</span>
		</div>
	</node-config-section>
</template>

<script setup lang="ts">
import { Delete, Plus } from '@element-plus/icons-vue';
import ClVariableInput from '../cl-variable-input.vue';
import NodeConfigSection from './node-config-section.vue';

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

<style scoped lang="scss">
.assignment-item {
	border: 1px solid var(--el-border-color-light);
	border-radius: 4px;
	padding: 10px;
	margin-bottom: 10px;
	background-color: var(--el-fill-color-blank);

	&:last-child {
		margin-bottom: 0;
	}
}
.assignment-header {
	display: flex;
	justify-content: space-between;
	align-items: center;
	margin-bottom: 10px;
	font-weight: bold;
	color: var(--el-text-color-regular);
}
.assignment-field {
	margin-bottom: 12px;
}
:deep(.assignment-field .el-form-item__label) {
	line-height: 22px;
	padding-bottom: 4px;
}
.empty-hint {
	font-size: 12px;
	color: var(--el-text-color-placeholder);
	text-align: center;
	padding: 16px 0;
	border: 1px dashed var(--el-border-color-lighter);
	border-radius: 6px;
	cursor: pointer;
	background: var(--el-fill-color-light);
	transition: all 0.2s;
	display: flex;
	align-items: center;
	justify-content: center;
	gap: 6px;

	&:hover {
		color: var(--el-color-primary);
		border-color: var(--el-color-primary-light-5);
		background: var(--el-color-primary-light-9);
	}

	.empty-icon {
		font-size: 14px;
	}
}
</style>
