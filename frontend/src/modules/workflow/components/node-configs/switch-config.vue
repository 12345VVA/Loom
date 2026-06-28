<template>
	<node-config-section :title="$t('条件分支')">
		<el-form-item :label="$t('匹配变量名')" required>
			<cl-variable-input v-model="config.variable" placeholder="例如: status" />
			<div class="field-hint">
				支持输入变量路径（如 variables.status 或 status）来进行值匹配。
			</div>
		</el-form-item>
		<el-form-item :label="$t('Case 分支列表')">
			<div v-for="(item, index) in config.cases || []" :key="index" class="case-item">
				<div class="case-row">
					<el-input
						v-model="item.value"
						:placeholder="'匹配值 ' + (Number(index) + 1)"
						size="small"
						class="case-value-input"
					/>
					<el-button
						type="danger"
						size="small"
						link
						:icon="Delete"
						@click="removeCase(index)"
					>
						{{ $t('删除') }}
					</el-button>
				</div>
			</div>
			<el-button
				type="primary"
				size="small"
				plain
				:icon="Plus"
				style="width: 100%"
				@click="addCase"
			>
				{{ $t('添加 Case 分支') }}
			</el-button>
		</el-form-item>
		<node-config-hint style="margin-top: 8px">
			<span
				>添加 Case
				后，节点右侧自动生成对应端口。从端口直接连线到目标节点，最后一个是默认路由。</span
			>
		</node-config-hint>
	</node-config-section>
</template>

<script setup lang="ts">
import { Delete, Plus } from '@element-plus/icons-vue';
import NodeConfigHint from './node-config-hint.vue';
import NodeConfigSection from './node-config-section.vue';
import ClVariableInput from '../cl-variable-input.vue';
import { useVueFlow } from '@vue-flow/core';
import { genId } from '../../utils';

const props = defineProps<{
	modelValue: Record<string, any>;
	nodeId?: string;
}>();

const config = props.modelValue;
const { getEdges, removeEdges } = useVueFlow();

function addCase() {
	if (!config.cases) {
		config.cases = [];
	}
	config.cases.push({ id: genId(), value: '' });
}

function removeCase(index: number) {
	const caseId = config.cases[index]?.id;
	if (props.nodeId && caseId != null) {
		// 稳定 handle：精确删除该 case 对应的边，其余边无需重编号
		const edgeToRemove = getEdges.value.find(
			(e) => e.source === props.nodeId && e.sourceHandle === `case_${caseId}`
		);
		if (edgeToRemove) {
			removeEdges([edgeToRemove.id]);
		}
	}
	config.cases.splice(index, 1);
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
</style>
