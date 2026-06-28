<template>
	<div class="tree-node-wrapper">
		<!-- 节点行 -->
		<div class="tree-node-row" :style="{ paddingLeft: `${depth * 14 + 6}px` }">
			<!-- Dify 风格引导折线 -->
			<div v-if="depth > 0" class="tree-connector">
				<div class="line-v" :class="{ 'is-last': isLast }"></div>
				<div class="line-h"></div>
			</div>

			<!-- 展开/折叠图标 -->
			<div class="col-expand-toggle">
				<el-icon
					v-if="isContainer"
					class="toggle-icon"
					:class="{ 'is-expanded': expanded }"
					@click="expanded = !expanded"
				>
					<caret-right />
				</el-icon>
			</div>

			<!-- 字段名 / 键名 -->
			<div class="col-name">
				<el-input
					v-model="node.name"
					size="small"
					style="width: 100%"
					:placeholder="placeholderText"
					:disabled="isNameDisabled"
				/>
			</div>

			<!-- 类型 -->
			<div class="col-type">
				<el-select
					v-model="node.type"
					size="small"
					style="width: 100%"
					@change="handleTypeChange"
				>
					<!-- Schema 模式类型选项 -->
					<template v-if="mode === 'schema'">
						<el-option label="str. String" value="string" />
						<el-option label="№ Number" value="number" />
						<el-option label="bool. Boolean" value="boolean" />
						<el-option label="{ } Object" value="object" />
						<el-option label="[{}] Array<Object>" value="array_object" />
						<el-option label="[str] Array<String>" value="array_string" />
						<el-option label="[№] Array<Number>" value="array_number" />
						<el-option label="[bool] Array<Boolean>" value="array_boolean" />
					</template>

					<!-- Value 模式类型选项 -->
					<template v-else>
						<el-option label="string" value="string" />
						<el-option label="number" value="number" />
						<el-option label="boolean" value="boolean" />
						<el-option label="object" value="object" />
						<el-option label="array" value="array" />
					</template>
				</el-select>
			</div>

			<!-- 值 / 描述 -->
			<div class="col-value-desc">
				<!-- Schema 模式下展示说明 -->
				<template v-if="mode === 'schema'">
					<el-input
						v-model="node.description"
						size="small"
						style="width: 100%"
						:placeholder="$t('字段描述 (可选)')"
					/>
				</template>

				<!-- Value 模式下，对于叶子类型，展示输入框 -->
				<template v-else>
					<el-input
						v-if="!isContainer"
						v-model="node.value"
						size="small"
						style="width: 100%"
						:placeholder="$t('值或 {变量}')"
					/>
					<span v-else class="container-placeholder">
						{{ node.type === 'object' ? '{ ... }' : '[ ... ]' }}
					</span>
				</template>
			</div>

			<!-- 操作 -->
			<div class="col-actions">
				<!-- 添加子项 (仅 container 类型可用) -->
				<el-button
					v-if="isContainer"
					type="primary"
					link
					:icon="Plus"
					size="small"
					@click="addChildNode"
				/>
				<!-- 删除节点 -->
				<el-button type="danger" link :icon="Delete" size="small" @click="deleteSelf" />
			</div>
		</div>

		<!-- 子节点列表 -->
		<div
			v-show="expanded && isContainer"
			class="tree-node-children"
		>
			<div class="children-list" v-if="node.children && node.children.length > 0">
				<cl-json-tree-node-item
					v-for="(child, idx) in node.children"
					:key="getStableKey(child)"
					:node="child"
					:depth="depth + 1"
					:index="Number(idx)"
					:parent-array="node.children"
					:parent-node="node"
					:mode="mode"
					@update="emit('update')"
				/>
			</div>
		</div>
	</div>
</template>

<script setup lang="ts">
import { ref, computed, watch } from 'vue';
import { Plus, Delete, CaretRight } from '@element-plus/icons-vue';

const props = defineProps<{
	node: any;
	depth: number;
	index: number;
	parentArray: any[];
	parentNode?: any;
	mode: 'schema' | 'value';
}>();

const emit = defineEmits(['update', 'update:node', 'trigger-update']);

function getStableKey(node: any): string {
	if (!node._keyId) {
		Object.defineProperty(node, '_keyId', {
			value: 'node_' + Math.random().toString(36).substring(2, 9),
			enumerable: false,
			configurable: false,
			writable: false
		});
	}
	return node._keyId;
}

const expanded = ref(true);

const isContainer = computed(() => {
	if (props.mode === 'schema') {
		return props.node.type === 'object' || props.node.type === 'array_object';
	} else {
		return props.node.type === 'object' || props.node.type === 'array';
	}
});

const isLast = computed(() => {
	return props.index === props.parentArray.length - 1;
});

const isNameDisabled = computed(() => {
	if (props.mode === 'schema') {
		return false;
	} else {
		return props.parentNode?.type === 'array';
	}
});

const placeholderText = computed(() => {
	if (props.mode === 'value' && props.parentNode?.type === 'array') {
		return props.index.toString();
	}
	return '字段名';
});

// 当父节点是 array 时，根据索引更新子节点的 name 属性
function updateArrayItemNames() {
	if (props.mode === 'value' && props.parentNode?.type === 'array') {
		props.node.name = `[${props.index}]`;
	}
}

// 监听 index 变化以重新生成 Value 模式下 Array 子项的索引名称
watch(
	() => props.index,
	() => {
		updateArrayItemNames();
	},
	{ immediate: true }
);

watch(
	() => props.parentNode?.type,
	() => {
		updateArrayItemNames();
	}
);

function handleTypeChange(val: string) {
	if (val === 'object' || val === 'array_object') {
		props.node.children = props.node.children || [];
		delete props.node.value;
	} else if (val === 'array') {
		props.node.children = props.node.children || [];
		delete props.node.value;
	} else {
		// 基础类型
		props.node.children = [];
		if (props.mode === 'value') {
			props.node.value = props.node.value ?? '';
		}
	}
	emit('update');
}

function addChildNode() {
	if (!props.node.children) {
		props.node.children = [];
	}

	if (props.node.type === 'array') {
		// Value 模式下的 Array 添加具体项
		const nextIndex = props.node.children.length;
		props.node.children.push({
			name: `[${nextIndex}]`,
			type: 'string',
			value: '',
			children: []
		});
	} else {
		// Object 或者是 Array<Object> 添加属性定义
		props.node.children.push({
			name: '',
			type: 'string',
			description: props.mode === 'schema' ? '' : undefined,
			value: props.mode === 'value' ? '' : undefined,
			children: []
		});
	}
	expanded.value = true;
	emit('update');
}

function deleteSelf() {
	props.parentArray.splice(props.index, 1);

	// 如果是 value 模式下的 array 子项，重算索引名
	if (props.mode === 'value' && props.parentNode?.type === 'array') {
		props.parentNode.children.forEach((child: any, idx: number) => {
			child.name = `[${idx}]`;
		});
	}

	emit('update');
}
</script>

<style lang="scss" scoped>
.tree-node-wrapper {
	position: relative;
}

.tree-node-row {
	display: flex;
	align-items: center;
	padding: 4px 6px;
	gap: 4px;
	transition: background-color 0.2s;
	position: relative;

	&:hover {
		background-color: var(--el-fill-color-extra-light);
	}

	/* Connector折线容器 */
	.tree-connector {
		position: absolute;
		left: -14px; /* 居中于父级 margin-left 14px */
		top: 0;
		bottom: 0;
		width: 14px;
		pointer-events: none;

		.line-v {
			position: absolute;
			left: 0;
			top: 0;
			bottom: 0;
			border-left: 1px solid var(--el-border-color-lighter);

			&.is-last {
				bottom: 50%; /* 终结于本行正中 */
			}
		}

		.line-h {
			position: absolute;
			left: 0;
			width: 14px;
			top: 50%;
			border-top: 1px solid var(--el-border-color-lighter);
		}
	}

	.col-expand-toggle {
		width: 16px;
		flex-shrink: 0;
		display: flex;
		justify-content: center;
		align-items: center;
		cursor: pointer;

		.toggle-icon {
			font-size: 11px;
			color: var(--el-text-color-placeholder);
			transition: transform 0.2s;

			&.is-expanded {
				transform: rotate(90deg);
			}
		}
	}

	.col-name {
		width: 110px;
		flex-shrink: 0;
	}

	.col-type {
		width: 85px;
		flex-shrink: 0;

		/* 微调 Element Plus 字体及内边距 */
		.el-select .el-input__inner {
			font-size: 11px;
		}
	}

	.col-value-desc {
		flex: 1;
		min-width: 60px;
		display: flex;
		align-items: center;

		.container-placeholder {
			font-size: 10px;
			color: var(--el-text-color-placeholder);
			font-family: monospace;
			user-select: none;
		}
	}

	.col-actions {
		width: 44px;
		flex-shrink: 0;
		display: flex;
		justify-content: flex-end;
		gap: 2px;
	}
}

.tree-node-children {
	position: relative;
	margin-left: 14px; /* 子节点相对父节点缩进对齐 */
}
</style>
