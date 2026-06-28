<template>
	<node-config-section :title="$t('输入')">
		<template #actions>
			<el-button type="primary" link size="small" :icon="Plus" @click.stop="addInput">{{
				$t('添加')
			}}</el-button>
		</template>
		<div class="node-inputs-editor">
			<div class="inputs-list">
				<div class="list-header" v-if="inputs.length">
					<span class="col-name">{{ $t('变量名') }}</span>
					<span class="col-value">{{ $t('变量值 (引用上游)') }}</span>
				</div>
				<div v-for="(item, index) in inputs" :key="index" class="input-item single-row">
					<div class="name-input-wrapper">
						<el-input
							v-model="item.name"
							:class="{ 'is-error': nameErrors[index] }"
							:placeholder="$t('例如: query')"
							size="small"
							class="name-input"
							@blur="validateName(index)"
						/>
						<div v-if="nameErrors[index]" class="name-error-tip">
							{{ nameErrors[index] }}
						</div>
					</div>

					<div class="value-group">
						<el-select
							v-model="item.type"
							size="small"
							class="type-select"
							:title="$t('数据类型')"
						>
							<el-option label="str" value="string" />
							<el-option label="num" value="number" />
							<el-option label="bool" value="boolean" />
							<el-option label="obj" value="object" />
							<el-option label="arr" value="array" />
						</el-select>

						<el-cascader
							v-model="item.source"
							:options="upstreamOptions"
							:props="{ expandTrigger: 'hover' }"
							:placeholder="$t('请选择')"
							size="small"
							class="source-cascader"
							clearable
						/>
					</div>

					<el-button
						link
						type="danger"
						:icon="Delete"
						@click="removeInput(index)"
						class="delete-btn"
					/>
				</div>
				<div v-if="!inputs.length" class="empty-hint" @click="addInput">
					<el-icon class="empty-icon"><plus /></el-icon>
					<span>{{ $t('暂无输入变量，点击添加') }}</span>
				</div>
			</div>
		</div>
	</node-config-section>
</template>

<script setup lang="ts">
import { computed, reactive, ref, watch } from 'vue';
import { Plus, Delete } from '@element-plus/icons-vue';
import { ElMessage } from 'element-plus';
import { cloneDeep, isEqual } from 'lodash-es';
import NodeConfigSection from './node-configs/node-config-section.vue';

const props = defineProps<{
	modelValue: any[];
	upstreamVars: any[];
}>();

const emit = defineEmits(['update:modelValue']);

const inputs = computed({
	get: () => props.modelValue || [],
	set: val => emit('update:modelValue', val)
});

// 变量名校验错误
const nameErrors = reactive<Record<number, string>>({});

const VALID_NAME_REGEX = /^[a-zA-Z_][a-zA-Z0-9_]*$/;

function validateName(index: number) {
	const name = (inputs.value[index]?.name || '').trim();
	delete nameErrors[index];

	if (!name) return;

	if (!VALID_NAME_REGEX.test(name)) {
		nameErrors[index] = '仅支持英文字母、数字和下划线';
		return;
	}

	// 去重校验
	const dupIndex = inputs.value.findIndex(
		(item, i) => i !== index && (item.name || '').trim() === name
	);
	if (dupIndex !== -1) {
		nameErrors[index] = `与第 ${dupIndex + 1} 行重复`;
	}
}

// 缓存上游变量
const cachedUpstreamVars = ref<any[]>([]);

watch(
	() => props.upstreamVars,
	(newVal) => {
		if (!isEqual(newVal, cachedUpstreamVars.value)) {
			cachedUpstreamVars.value = cloneDeep(newVal || []);
		}
	},
	{ immediate: true, deep: true }
);

// Convert flat upstreamVars into cascader options
const upstreamOptions = computed(() => {
	const map = new Map<string, any>();
	(cachedUpstreamVars.value || []).forEach(v => {
		if (!map.has(v.nodeId)) {
			map.set(v.nodeId, {
				value: v.nodeId,
				label: v.nodeLabel || v.nodeId,
				children: []
			});
		}
		map.get(v.nodeId).children.push({
			value: v.variableName, // e.g., 'text' or 'output.topic'
			label: v.display || v.key
		});
	});
	return Array.from(map.values());
});

function addInput() {
	const currentInputs = [...inputs.value];
	let newName = 'input_1';
	let counter = 1;

	// 去重逻辑：寻找未被占用的名称
	while (currentInputs.some(item => item.name === newName)) {
		counter++;
		newName = `input_${counter}`;
	}

	currentInputs.push({
		name: newName,
		type: 'string',
		source: []
	});
	inputs.value = currentInputs;
}

function removeInput(index: number) {
	const currentInputs = [...inputs.value];
	currentInputs.splice(index, 1);
	inputs.value = currentInputs;
	delete nameErrors[index];
	// 重新校验剩余项
	Object.keys(nameErrors).forEach(k => {
		const i = Number(k);
		if (i < currentInputs.length) {
			validateName(i);
		} else {
			delete nameErrors[i];
		}
	});
}
</script>

<style scoped lang="scss">
.node-inputs-editor {
	margin-bottom: 0;
	background: transparent;

	.inputs-list {
		padding: 12px;

		.list-header {
			display: flex;
			font-size: 12px;
			color: var(--el-text-color-secondary);
			margin-bottom: 8px;
			padding: 0 4px;

			.col-name {
				flex: 1;
			}
			.col-value {
				flex: 1.5;
				margin-left: 8px;
			}
		}

		.input-item.single-row {
			display: flex;
			align-items: flex-start;
			gap: 6px;
			margin-bottom: 8px;

			&:last-child {
				margin-bottom: 0;
			}

			.name-input-wrapper {
				flex: 1;
				min-width: 0;

				.name-error-tip {
					font-size: 11px;
					color: var(--el-color-danger);
					line-height: 1.4;
					margin-top: 2px;
				}
			}

			.name-input {
				width: 100%;
			}

			.value-group {
				flex: 1.5;
				display: flex;
				align-items: center;
				border: 1px solid var(--el-border-color);
				border-radius: 4px;
				overflow: hidden;
				transition: border-color 0.2s;

				&:hover,
				&:focus-within {
					border-color: var(--el-color-primary);
				}

				.type-select {
					width: 65px;

					:deep(.el-input__wrapper) {
						box-shadow: none !important;
						border-radius: 0;
						background-color: var(--el-fill-color-light);
						padding: 0 8px;
					}
					:deep(.el-input__inner) {
						text-align: center;
						font-size: 12px;
					}
				}

				.source-cascader {
					flex: 1;
					min-width: 0;

					:deep(.el-input__wrapper) {
						box-shadow: none !important;
						border-radius: 0;
						border-left: 1px solid var(--el-border-color-lighter);
					}
				}
			}

			.delete-btn {
				padding: 4px;
				margin-left: 2px;
				margin-top: 6px;
				font-size: 16px;
			}
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
	}
}
</style>
