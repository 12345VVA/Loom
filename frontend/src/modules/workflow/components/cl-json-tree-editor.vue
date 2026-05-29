<template>
	<div class="cl-json-tree-editor">
		<div class="tree-header">
			<div class="col-name">{{ $t('字段/键名') }}</div>
			<div class="col-type">{{ $t('类型') }}</div>
			<div class="col-value-desc">{{ mode === 'schema' ? $t('字段说明 (可选)') : $t('值 (可引用变量)') }}</div>
			<div class="col-actions"></div>
		</div>

		<div class="tree-body">
			<template v-if="modelValue && modelValue.length > 0">
				<tree-node-item
					v-for="(node, idx) in modelValue"
					:key="idx"
					:node="node"
					:depth="0"
					:index="idx"
					:parent-array="modelValue"
					:mode="mode"
					@update="triggerUpdate"
				/>
			</template>
			<div v-else class="empty-tip">
				{{ $t('暂无字段，请点击下方按钮添加') }}
			</div>
		</div>

		<div class="tree-footer">
			<el-button type="primary" link :icon="Plus" @click="addRootNode">
				{{ mode === 'schema' ? $t('添加根字段') : $t('添加根键值对') }}
			</el-button>
			<el-divider direction="vertical" />
			<el-button type="info" link :icon="DocumentCopy" @click="copyJson">
				{{ $t('复制 JSON') }}
			</el-button>
			<el-button type="success" link :icon="Upload" @click="openImportDialog">
				{{ $t('导入 JSON') }}
			</el-button>
		</div>

		<!-- 导入 JSON 弹窗 -->
		<el-dialog
			v-model="importVisible"
			:title="$t('导入 JSON 数据')"
			width="460px"
			append-to-body
			destroy-on-close
		>
			<div style="font-size: 12px; color: var(--el-text-color-secondary); margin-bottom: 12px;">
				{{ mode === 'schema' 
					? $t('请输入一个标准的 JSON 对象，系统将自动分析其键名和类型并生成相应的 Schema。') 
					: $t('请输入要导入的 JSON，系统将自动还原为键值对数据结构。')
				}}
			</div>
			<el-input
				v-model="importText"
				type="textarea"
				:rows="10"
				placeholder='{ "key": "value" }'
			/>
			<template #footer>
				<el-button size="small" @click="importVisible = false">{{ $t('取消') }}</el-button>
				<el-button size="small" type="primary" @click="confirmImport">{{ $t('确定') }}</el-button>
			</template>
		</el-dialog>
	</div>
</template>

<script setup lang="ts">
import { ref } from 'vue';
import { Plus, DocumentCopy, Upload } from '@element-plus/icons-vue';
import { ElMessage } from 'element-plus';
import { useI18n } from 'vue-i18n';
import TreeNodeItem from './cl-json-tree-node-item.vue';

const props = withDefaults(
	defineProps<{
		modelValue: any[];
		mode?: 'schema' | 'value';
	}>(),
	{
		mode: 'schema'
	}
);

const emit = defineEmits(['update:modelValue', 'change']);
const { t } = useI18n();

function triggerUpdate() {
	emit('update:modelValue', [...props.modelValue]);
	emit('change', [...props.modelValue]);
}

function addRootNode() {
	const newList = [...(props.modelValue || [])];
	if (props.mode === 'schema') {
		newList.push({
			name: '',
			type: 'string',
			description: '',
			children: []
		});
	} else {
		newList.push({
			name: '',
			type: 'string',
			value: '',
			children: []
		});
	}
	emit('update:modelValue', newList);
	emit('change', newList);
}

// --- 一键复制 & JSON 导入逻辑 ---
const importVisible = ref(false);
const importText = ref('');

function buildJson(children: any[]): any {
	const obj: Record<string, any> = {};
	for (const child of children) {
		if (!child.name) continue;
		if (child.type === 'object') {
			obj[child.name] = buildJson(child.children || []);
		} else if (child.type === 'array') {
			obj[child.name] = buildArray(child.children || []);
		} else {
			obj[child.name] = child.value || '';
		}
	}
	return obj;
}

function buildArray(children: any[]): any[] {
	return (children || []).map(child => {
		if (child.type === 'object') {
			return buildJson(child.children || []);
		} else if (child.type === 'array') {
			return buildArray(child.children || []);
		} else {
			return child.value || '';
		}
	});
}

function buildMockJson(children: any[]): any {
	const obj: Record<string, any> = {};
	for (const child of children) {
		if (!child.name || child.name === '[Item]') continue;
		if (child.type === 'object') {
			obj[child.name] = buildMockJson(child.children || []);
		} else if (child.type === 'array_object') {
			obj[child.name] = [buildMockJson(child.children || [])];
		} else if (child.type === 'array_string') {
			obj[child.name] = ['string'];
		} else if (child.type === 'array_number') {
			obj[child.name] = [0];
		} else if (child.type === 'array_boolean') {
			obj[child.name] = [true];
		} else if (child.type === 'number') {
			obj[child.name] = 0;
		} else if (child.type === 'boolean') {
			obj[child.name] = true;
		} else {
			obj[child.name] = child.description || 'string';
		}
	}
	return obj;
}

function copyJson() {
	const fields = props.modelValue || [];
	if (fields.length === 0) {
		ElMessage.warning(t('暂无内容可复制'));
		return;
	}
	let serialized = '';
	if (props.mode === 'schema') {
		const obj = buildMockJson(fields);
		serialized = JSON.stringify(obj, null, 2);
	} else {
		const obj = buildJson(fields);
		serialized = JSON.stringify(obj, null, 2);
	}
	navigator.clipboard.writeText(serialized).then(() => {
		ElMessage.success(t('JSON 已复制到剪贴板'));
	}).catch(() => {
		ElMessage.error(t('复制失败'));
	});
}

function openImportDialog() {
	importText.value = '';
	importVisible.value = true;
}

function jsonToSchemaNodes(val: any, name: string = ''): any {
	if (val === null || val === undefined) {
		return { name, type: 'string', description: '', children: [] };
	}
	
	const t = typeof val;
	if (t === 'string') {
		return { name, type: 'string', description: '', children: [] };
	} else if (t === 'number') {
		return { name, type: 'number', description: '', children: [] };
	} else if (t === 'boolean') {
		return { name, type: 'boolean', description: '', children: [] };
	} else if (Array.isArray(val)) {
		if (val.length === 0) {
			return { name, type: 'array_string', description: '', children: [] };
		}
		const first = val[0];
		const firstType = typeof first;
		if (firstType === 'object' && first !== null) {
			const childNodes: any[] = [];
			for (const [k, v] of Object.entries(first)) {
				childNodes.push(jsonToSchemaNodes(v, k));
			}
			return { name, type: 'array_object', description: '', children: childNodes };
		} else if (firstType === 'number') {
			return { name, type: 'array_number', description: '', children: [] };
		} else if (firstType === 'boolean') {
			return { name, type: 'array_boolean', description: '', children: [] };
		} else {
			return { name, type: 'array_string', description: '', children: [] };
		}
	} else if (t === 'object') {
		const childNodes: any[] = [];
		for (const [k, v] of Object.entries(val)) {
			childNodes.push(jsonToSchemaNodes(v, k));
		}
		return { name, type: 'object', children: childNodes };
	}
	return { name, type: 'string', description: '', children: [] };
}

function importJsonToSchema(val: any): any[] {
	if (val && typeof val === 'object' && !Array.isArray(val)) {
		const result: any[] = [];
		for (const [k, v] of Object.entries(val)) {
			result.push(jsonToSchemaNodes(v, k));
		}
		return result;
	}
	return [jsonToSchemaNodes(val, 'root')];
}

function jsonToValueNodes(val: any, name: string = ''): any {
	if (val === null || val === undefined) {
		return { name, type: 'string', value: '', children: [] };
	}
	
	const t = typeof val;
	if (t === 'string' || t === 'number' || t === 'boolean') {
		return { name, type: t, value: String(val), children: [] };
	} else if (Array.isArray(val)) {
		const childNodes = val.map((item, idx) => {
			return jsonToValueNodes(item, `[${idx}]`);
		});
		return { name, type: 'array', children: childNodes };
	} else if (t === 'object') {
		const childNodes: any[] = [];
		for (const [k, v] of Object.entries(val)) {
			childNodes.push(jsonToValueNodes(v, k));
		}
		return { name, type: 'object', children: childNodes };
	}
	return { name, type: 'string', value: '', children: [] };
}

function importJsonToValue(val: any): any[] {
	if (val && typeof val === 'object' && !Array.isArray(val)) {
		const result: any[] = [];
		for (const [k, v] of Object.entries(val)) {
			result.push(jsonToValueNodes(v, k));
		}
		return result;
	}
	return [jsonToValueNodes(val, 'root')];
}

function confirmImport() {
	if (!importText.value.trim()) {
		ElMessage.warning(t('请输入 JSON 字符串'));
		return;
	}
	try {
		const parsed = JSON.parse(importText.value.trim());
		let importedNodes: any[] = [];
		if (props.mode === 'schema') {
			importedNodes = importJsonToSchema(parsed);
		} else {
			importedNodes = importJsonToValue(parsed);
		}
		emit('update:modelValue', importedNodes);
		emit('change', importedNodes);
		importVisible.value = false;
		ElMessage.success(t('JSON 导入成功'));
	} catch (e: any) {
		ElMessage.error(t('JSON 解析失败: ') + e.message);
	}
}
</script>

<style lang="scss" scoped>
.cl-json-tree-editor {
	border: 1px solid var(--el-border-color-lighter);
	border-radius: 6px;
	background-color: var(--el-fill-color-blank);
	overflow: hidden;
	margin-bottom: 8px;

	.tree-header {
		display: flex;
		background-color: var(--el-fill-color-light);
		padding: 8px 6px;
		padding-left: 22px; /* 6px padding + 16px toggle size */
		font-size: 11px;
		font-weight: 600;
		color: var(--el-text-color-secondary);
		border-bottom: 1px solid var(--el-border-color-lighter);
		gap: 4px;

		.col-name {
			width: 90px;
			flex-shrink: 0;
		}
		.col-type {
			width: 70px;
			flex-shrink: 0;
		}
		.col-value-desc {
			flex: 1;
			min-width: 60px;
		}
		.col-actions {
			width: 44px;
			flex-shrink: 0;
		}
	}

	.tree-body {
		padding: 4px 0;
		min-height: 50px;
	}

	.empty-tip {
		padding: 20px;
		text-align: center;
		color: var(--el-text-color-placeholder);
		font-size: 12px;
	}

	.tree-footer {
		padding: 6px 12px;
		border-top: 1px dashed var(--el-border-color-lighter);
		background-color: var(--el-fill-color-extra-light);
	}
}
</style>
