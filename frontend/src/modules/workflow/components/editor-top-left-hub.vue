<template>
	<div class="editor-top-left-hub" @contextmenu.prevent>
		<!-- 1. 工程与操作菜单 -->
		<el-tooltip
			:content="$t('工程菜单')"
			placement="bottom"
			:show-after="200"
			:disabled="dropdownVisible"
		>
			<div class="hub-item-wrap">
				<el-dropdown
					trigger="click"
					@command="handleMenuCommand"
					@visible-change="(val: boolean) => (dropdownVisible = val)"
				>
					<el-button class="hub-btn icon-btn" text :icon="Menu" />
					<template #dropdown>
						<el-dropdown-menu class="hub-dropdown-menu">
							<el-dropdown-item command="export" :icon="Download">
								{{ $t('导出工作流 (JSON)') }}
							</el-dropdown-item>
							<el-dropdown-item command="shortcuts" :icon="Key">
								{{ $t('快捷键指南') }}
							</el-dropdown-item>
							<el-dropdown-item command="info" :icon="InfoFilled" divided v-if="workflowName || workflowCode">
								{{ $t('工作流信息') }}
							</el-dropdown-item>
						</el-dropdown-menu>
					</template>
				</el-dropdown>
			</div>
		</el-tooltip>

		<el-divider direction="vertical" class="hub-divider" />

		<!-- 2. 添加节点主入口 -->
		<el-tooltip
			:content="$t('添加节点')"
			placement="bottom"
			:show-after="200"
			:disabled="popoverVisible"
		>
			<div class="hub-item-wrap">
				<el-popover
					placement="bottom-start"
					:width="360"
					trigger="click"
					v-model:visible="popoverVisible"
					popper-class="node-selector-popover"
					@show="onPopoverShow"
				>
					<template #reference>
						<el-button
							type="primary"
							class="hub-btn add-node-btn icon-btn"
							:icon="Plus"
						/>
					</template>

					<div class="node-selector-container">
				<el-input
					v-model="nodeSearch"
					:prefix-icon="Search"
					:placeholder="$t('搜索节点、插件、工作流...')"
					clearable
					size="default"
					class="node-search"
					ref="searchInputRef"
				/>

				<div class="node-categories">
					<template v-for="category in filteredCategories" :key="category.name">
						<div class="category-title" v-if="category.items.length > 0">
							{{ category.name }}
						</div>
						<div class="node-grid" v-if="category.items.length > 0">
							<div
								v-for="item in category.items"
								:key="item.type"
								class="node-template-item"
								:class="'node-template-item--' + item.type"
								draggable="true"
								@dragstart="onDragStart($event, item.type)"
								@click="onClickNode(item.type)"
								:title="item.desc"
							>
								<el-icon class="template-icon">
									<component :is="item.icon" />
								</el-icon>
								<span class="template-name">{{ item.name }}</span>
							</div>
						</div>
					</template>
					<el-empty
						v-if="isSearchEmpty"
						:image-size="60"
						:description="$t('暂无匹配的节点')"
					/>
				</div>
			</div>
		</el-popover>
	</div>
</el-tooltip>

		<el-divider direction="vertical" class="hub-divider" />

		<!-- 3. 视图控制 (MiniMap 缩略图切换) -->
		<el-tooltip
			:content="miniMapVisible ? $t('隐藏缩略图') : $t('显示缩略图')"
			placement="bottom"
		>
			<el-button
				class="hub-btn minimap-btn"
				text
				:class="{ 'is-active': miniMapVisible }"
				:icon="Grid"
				@click="$emit('toggle-minimap')"
			/>
		</el-tooltip>

		<!-- 快捷键指南对话框 -->
		<el-dialog
			v-model="shortcutsDialogVisible"
			:title="$t('画布快捷键指南')"
			width="460px"
			append-to-body
		>
			<div class="shortcuts-list">
				<div
					v-for="(item, index) in shortcutsList"
					:key="index"
					class="shortcut-item"
				>
					<span class="shortcut-desc">{{ item.desc }}</span>
					<div class="shortcut-keys">
						<kbd v-for="(k, ki) in item.keys" :key="ki">{{ k }}</kbd>
					</div>
				</div>
			</div>
			<template #footer>
				<el-button @click="shortcutsDialogVisible = false">{{ $t('关闭') }}</el-button>
			</template>
		</el-dialog>

		<!-- 工作流信息对话框 -->
		<el-dialog
			v-model="infoDialogVisible"
			:title="$t('工作流信息')"
			width="420px"
			append-to-body
		>
			<div class="workflow-info-content">
				<div class="info-row">
					<span class="info-label">{{ $t('工作流名称') }}:</span>
					<span class="info-value font-medium">{{ workflowName || $t('未命名工作流') }}</span>
				</div>
				<div class="info-row" v-if="workflowCode">
					<span class="info-label">{{ $t('工作流编码') }}:</span>
					<el-tag size="small" type="info">{{ workflowCode }}</el-tag>
				</div>
			</div>
			<template #footer>
				<el-button type="primary" @click="infoDialogVisible = false">{{ $t('确定') }}</el-button>
			</template>
		</el-dialog>
	</div>
</template>

<script lang="ts" setup>
import { ref, computed, nextTick, markRaw } from 'vue';
import { useI18n } from 'vue-i18n';
import {
	Menu,
	Plus,
	Search,
	Grid,
	Download,
	Key,
	InfoFilled
} from '@element-plus/icons-vue';
import { NODE_REGISTRY } from '../utils/node-type-registry';

const props = defineProps<{
	miniMapVisible: boolean;
	workflowName?: string;
	workflowCode?: string;
}>();

const emit = defineEmits<{
	(e: 'add-node', type: string): void;
	(e: 'drag-start', event: DragEvent, type: string): void;
	(e: 'toggle-minimap'): void;
	(e: 'export-workflow'): void;
}>();

const { t } = useI18n();

// 菜单状态
const dropdownVisible = ref(false);

// 节点选择器
const popoverVisible = ref(false);
const nodeSearch = ref('');
const searchInputRef = ref<{ focus: () => void } | null>(null);

// 弹窗状态
const shortcutsDialogVisible = ref(false);
const infoDialogVisible = ref(false);

const isMac = typeof navigator !== 'undefined' && /Mac|iPod|iPhone|iPad/.test(navigator.platform);
const modKey = isMac ? '⌘' : 'Ctrl';

const shortcutsList = computed(() => [
	{ desc: t('保存工作流'), keys: [modKey, 'S'] },
	{ desc: t('撤销操作'), keys: [modKey, 'Z'] },
	{ desc: t('重做操作'), keys: [modKey, 'Shift', 'Z'] },
	{ desc: t('删除选中节点/边'), keys: ['Delete / Backspace'] },
	{ desc: t('多选/全选节点'), keys: [modKey, 'A'] },
	{ desc: t('复制节点'), keys: [modKey, 'D'] },
	{ desc: t('画布缩放'), keys: [t('滚轮')] },
	{ desc: t('画布平移'), keys: [t('鼠标按住背景拖动')] }
]);

const categories = computed(() => {
	const cats = [
		{ name: t('基础'), key: 'basic' },
		{ name: t('模型与插件'), key: 'ai' },
		{ name: t('业务逻辑'), key: 'logic' },
		{ name: t('输入与输出'), key: 'system' }
	];

	return cats.map(cat => {
		const items = NODE_REGISTRY.filter(n => {
			if ((n as { deprecated?: boolean }).deprecated) return false;
			if (cat.key === 'basic') return n.type === 'start' || n.type === 'end';
			return n.category === cat.key && n.type !== 'start' && n.type !== 'end';
		}).map(n => ({
			type: n.type,
			name: t(n.labelKey),
			desc: n.descKey ? t(n.descKey) : '',
			icon: markRaw(n.icon)
		}));
		return { name: cat.name, items };
	});
});

const filteredCategories = computed(() => {
	const q = nodeSearch.value.trim().toLowerCase();
	if (!q) return categories.value;

	return categories.value.map(cat => ({
		...cat,
		items: cat.items.filter(
			item => item.name.toLowerCase().includes(q) || item.desc.toLowerCase().includes(q)
		)
	}));
});

const isSearchEmpty = computed(() => {
	return filteredCategories.value.every(cat => cat.items.length === 0);
});

function handleMenuCommand(command: string) {
	if (command === 'export') {
		emit('export-workflow');
	} else if (command === 'shortcuts') {
		shortcutsDialogVisible.value = true;
	} else if (command === 'info') {
		infoDialogVisible.value = true;
	}
}

function onDragStart(event: DragEvent, type: string) {
	emit('drag-start', event, type);
}

function onClickNode(type: string) {
	emit('add-node', type);
	popoverVisible.value = false;
}

function onPopoverShow() {
	nextTick(() => {
		searchInputRef.value?.focus();
	});
}
</script>

<style lang="scss" scoped>
.editor-top-left-hub {
	position: absolute;
	top: 16px;
	left: 16px;
	z-index: 5;
	display: flex;
	align-items: center;
	gap: 4px;
	padding: 3px 6px;
	background: rgba(255, 255, 255, 0.88);
	backdrop-filter: blur(12px);
	border: 1px solid var(--el-border-color-light);
	border-radius: 8px;
	box-shadow: 0 4px 16px rgba(0, 0, 0, 0.08);
	transition: all 0.2s ease;

	&:hover {
		box-shadow: 0 6px 20px rgba(0, 0, 0, 0.12);
	}
}

.hub-item-wrap {
	display: inline-flex;
	align-items: center;
	justify-content: center;
}

.hub-btn {
	width: 30px;
	height: 30px;
	padding: 0;
	display: inline-flex;
	align-items: center;
	justify-content: center;
	border-radius: 6px;
	font-size: 15px;
	color: var(--el-text-color-primary);

	&:hover {
		background: var(--el-fill-color-light);
	}
}

.add-node-btn {
	font-size: 15px;
}

.hub-divider {
	height: 14px;
	margin: 0 1px;
}

.minimap-btn {
	font-size: 15px;
	color: var(--el-text-color-secondary);

	&.is-active {
		color: var(--el-color-primary);
		background: var(--el-color-primary-light-9);
	}
}

// 节点选择器弹窗内样式
.node-selector-container {
	display: flex;
	flex-direction: column;
	gap: 12px;
	max-height: 500px;
}

.node-categories {
	overflow-y: auto;
	padding-right: 4px;

	&::-webkit-scrollbar {
		width: 6px;
	}
	&::-webkit-scrollbar-thumb {
		background: var(--el-border-color-darker);
		border-radius: 3px;
	}
}

.category-title {
	font-size: 12px;
	color: var(--el-text-color-secondary);
	margin-bottom: 8px;
	margin-top: 12px;
	font-weight: 500;

	&:first-child {
		margin-top: 0;
	}
}

.node-grid {
	display: grid;
	grid-template-columns: repeat(2, 1fr);
	gap: 8px;
}

.node-template-item {
	display: flex;
	align-items: center;
	gap: 8px;
	padding: 8px 12px;
	background-color: var(--el-fill-color-blank);
	border: 1px solid var(--el-border-color-light);
	border-radius: 6px;
	cursor: pointer;
	transition: all 0.2s ease;
	user-select: none;

	&:hover {
		background-color: var(--el-color-primary-light-9);
		border-color: var(--el-color-primary-light-5);
		color: var(--el-color-primary);

		.template-icon {
			color: var(--el-color-primary);
		}
	}

	&:active {
		cursor: grabbing;
	}

	.template-icon {
		font-size: 16px;
		color: var(--el-text-color-regular);
		transition: color 0.2s;
	}

	.template-name {
		font-size: 13px;
		font-weight: 500;
		color: inherit;
	}

	&--start {
		border-left: 3px solid var(--el-color-success);
	}
	&--llm {
		border-left: 3px solid var(--el-color-primary);
	}
	&--tool {
		border-left: 3px solid #8a2be2;
	}
	&--condition {
		border-left: 3px solid var(--el-color-warning);
	}
	&--switch {
		border-left: 3px solid #e6a23c;
	}
	&--human_input {
		border-left: 3px solid var(--el-color-info);
	}
	&--intent_classifier {
		border-left: 3px solid #20b2aa;
	}
	&--loop_controller {
		border-left: 3px solid #d2691e;
	}
	&--batch_processor {
		border-left: 3px solid #00ced1;
	}
	&--image_generator {
		border-left: 3px solid #ff69b4;
	}
	&--tool_executor {
		border-left: 3px solid #8a2be2;
	}
	&--end {
		border-left: 3px solid var(--el-color-danger);
	}
}

// 快捷键列表弹窗样式
.shortcuts-list {
	display: flex;
	flex-direction: column;
	gap: 12px;
}

.shortcut-item {
	display: flex;
	align-items: center;
	justify-content: space-between;
	padding: 6px 8px;
	border-radius: 6px;
	background: var(--el-fill-color-light);

	.shortcut-desc {
		font-size: 13px;
		color: var(--el-text-color-primary);
	}

	.shortcut-keys {
		display: flex;
		align-items: center;
		gap: 4px;

		kbd {
			padding: 2px 6px;
			font-size: 12px;
			font-family: inherit;
			color: var(--el-text-color-primary);
			background-color: var(--el-fill-color-blank);
			border: 1px solid var(--el-border-color-dark);
			border-radius: 4px;
			box-shadow: 0 1px 1px rgba(0, 0, 0, 0.1);
		}
	}
}

// 工作流基础信息样式
.workflow-info-content {
	display: flex;
	flex-direction: column;
	gap: 14px;

	.info-row {
		display: flex;
		align-items: center;
		gap: 8px;
		font-size: 14px;

		.info-label {
			color: var(--el-text-color-secondary);
			width: 80px;
		}

		.info-value {
			color: var(--el-text-color-primary);
		}
	}
}
</style>
