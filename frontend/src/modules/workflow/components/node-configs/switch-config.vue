<template>
	<el-form-item :label="$t('匹配变量名')" required>
		<cl-variable-input v-model="config.variable" placeholder="例如: status" />
		<div class="field-hint">
			支持输入变量路径（如 variables.status 或 status）来进行值匹配。
		</div>
	</el-form-item>
	<el-form-item :label="$t('Case 分支列表')">
		<div
			v-for="(item, index) in (config.cases || [])"
			:key="index"
			class="case-item">
			<div class="case-row">
				<el-input v-model="item.value" :placeholder="'匹配值 ' + (Number(index) + 1)" size="small" class="case-value-input" />
				<el-button type="danger" size="small" link :icon="Delete" @click="config.cases.splice(index, 1)">
					{{ $t('删除') }}
				</el-button>
			</div>
		</div>
		<el-button type="primary" size="small" plain :icon="Plus" style="width: 100%" @click="addCase">
			{{ $t('添加 Case 分支') }}
		</el-button>
	</el-form-item>
	<div class="config-hint">
		<el-icon><info-filled /></el-icon>
		<span>添加 Case 后，节点右侧自动生成对应端口。从端口直接连线到目标节点，最后一个是默认路由。</span>
	</div>
</template>

<script setup lang="ts">
import { Delete, Plus, InfoFilled } from '@element-plus/icons-vue';
import ClVariableInput from '../cl-variable-input.vue';

const props = defineProps<{
	modelValue: Record<string, any>;
}>();

const config = props.modelValue;

function addCase() {
	if (!config.cases) {
		config.cases = [];
	}
	config.cases.push({ value: '' });
}
</script>

<style lang="scss" scoped>
.field-hint {
	font-size: 11px;
	color: var(--el-text-color-placeholder);
	margin-top: 4px;
	line-height: 1.4;
}

.case-item {
	border: 1px solid var(--el-border-color-lighter);
	padding: 8px 10px;
	margin-bottom: 8px;
	border-radius: 6px;
}

.case-row {
	display: flex;
	align-items: center;
	gap: 8px;
}

.case-value-input {
	flex: 1;
}

.config-hint {
	display: flex;
	align-items: flex-start;
	gap: 6px;
	padding: 8px 10px;
	background: var(--el-fill-color-light);
	border-radius: 6px;
	border: 1px solid var(--el-border-color-lighter);
	font-size: 12px;
	color: var(--el-text-color-secondary);
	line-height: 1.5;

	.el-icon {
		margin-top: 2px;
		color: var(--el-color-info);
		flex-shrink: 0;
	}
}
</style>
