<template>
	<node-config-section :title="$t('全局输入')">
		<el-form-item :label="$t('工作流输入变量')" style="margin-bottom: 0">
			<div class="field-hint" style="margin-bottom: 8px">
				定义工作流启动时接收的变量名，下游节点可引用。可选的「默认值」在运行/试运行时自动预填，留空则视为无默认值。
			</div>
			<div
				v-for="(row, index) in rows"
				:key="index"
				style="display: flex; gap: 6px; margin-bottom: 6px; align-items: flex-start"
			>
				<div style="flex: 1">
					<el-input
						v-model="row.name"
						:class="{ 'is-error': getVarError(index) }"
						placeholder="变量名 (如 query)"
						size="small"
						@blur="validateVar(index)"
						@input="commit"
					/>
					<div v-if="getVarError(index)" class="var-error-tip">
						{{ getVarError(index) }}
					</div>
				</div>
				<div style="flex: 1">
					<el-input
						v-model="row.defaultText"
						placeholder="默认值 (可留空)"
						size="small"
						@input="commit"
					/>
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
import { reactive, ref } from 'vue';
import { Delete, Plus } from '@element-plus/icons-vue';
import NodeConfigSection from './node-config-section.vue';

const props = defineProps<{
	modelValue: Record<string, any>;
}>();

const emit = defineEmits(['update:modelValue']);

const config = props.modelValue;

interface InputRow {
	name: string;
	defaultText: string;
}

// 变量名校验错误状态
const varErrors = reactive<Record<number, string>>({});

const VALID_NAME_REGEX = /^[a-zA-Z_][a-zA-Z0-9_]*$/;

/** 数字/布尔字面量按原类型存回，避免把 10 变成 "10"；其余保持字符串。 */
function coerceDefault(raw: string): unknown {
	const t = raw.trim();
	if (/^-?\d+(\.\d+)?$/.test(t)) return Number(t);
	if (t === 'true') return true;
	if (t === 'false') return false;
	return raw;
}

function toText(v: unknown): string {
	if (v === undefined || v === null) return '';
	if (typeof v === 'object') return JSON.stringify(v);
	return String(v);
}

/** 兼容旧写法（string[]）与新写法（[{name, default}]），统一为可编辑行。 */
function buildRows(): InputRow[] {
	const list = config.inputVariables;
	if (!Array.isArray(list)) return [];
	return list.map(item => {
		if (typeof item === 'string') return { name: item, defaultText: '' };
		if (item && typeof item === 'object') {
			return {
				name: String(item.name ?? ''),
				defaultText: Object.prototype.hasOwnProperty.call(item, 'default')
					? toText(item.default)
					: ''
			};
		}
		return { name: '', defaultText: '' };
	});
}

const rows = ref<InputRow[]>(buildRows());

/** 行 → config.inputVariables（空默认值不落 default 键，与后端「仅在存在 default 时生效」一致）。 */
function commit() {
	config.inputVariables = rows.value.map(row => {
		const name = row.name;
		if (row.defaultText.trim() === '') return { name };
		return { name, default: coerceDefault(row.defaultText) };
	});
	emit('update:modelValue', config);
}

function validateVar(index: number) {
	const name = (rows.value[index]?.name || '').trim();
	delete varErrors[index];

	if (!name) return; // 空值不校验（用户可能正在编辑）

	if (!VALID_NAME_REGEX.test(name)) {
		varErrors[index] = '变量名仅支持英文字母、数字和下划线，且不能以数字开头';
		return;
	}

	// 去重校验
	const duplicateIndex = rows.value.findIndex(
		(r, i) => i !== index && r.name.trim() === name
	);
	if (duplicateIndex !== -1) {
		varErrors[index] = `变量名与第 ${duplicateIndex + 1} 个重复`;
	}
}

function getVarError(index: number): string {
	return varErrors[index] || '';
}

function addVariable() {
	rows.value.push({ name: '', defaultText: '' });
	commit();
}

function removeVariable(index: number) {
	rows.value.splice(index, 1);
	delete varErrors[index];
	// 重新校验剩余变量（去重索引可能变化）
	Object.keys(varErrors).forEach(k => {
		const i = Number(k);
		if (i >= rows.value.length) {
			delete varErrors[i];
		} else {
			validateVar(i);
		}
	});
	commit();
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
