<template>
	<div class="editor-bottom-toolbar" @contextmenu.prevent :style="toolbarStyle">
		<div class="toolbar-left">
			<span class="workflow-title">{{ workflowName || $t('未命名工作流') }}</span>
			<el-tag size="small" type="info" class="workflow-code">{{ workflowCode }}</el-tag>
			<el-divider direction="vertical" class="mx-2" style="margin: 0 8px" />
			<el-popover
				placement="top"
				:width="360"
				trigger="click"
				v-model:visible="popoverVisible"
				popper-class="node-selector-popover"
				@show="onPopoverShow"
			>
				<template #reference>
					<el-button type="primary" plain class="add-node-btn" :icon="Plus">
						{{ $t('添加节点') }}
					</el-button>
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
			<el-button style="margin-left: 8px" @click="$emit('export-workflow')" :icon="Download">
				{{ $t('导出') }}
			</el-button>
		</div>

		<div class="toolbar-right">
			<template v-if="testLogDrawerInstanceId">
				<el-button plain type="info" @click="$emit('clear-test-status')">
					<el-icon><brush /></el-icon>{{ $t('清除') }}
				</el-button>
				<el-button plain type="primary" @click="$emit('reopen-test-log-drawer')">
					<el-icon><document /></el-icon>{{ $t('日志') }}
				</el-button>
				<el-divider direction="vertical" style="margin: 0 8px" />
			</template>

			<el-tooltip :content="$t('撤销 (Ctrl+Z)')" placement="top">
				<el-button link :icon="RefreshLeft" :disabled="!canUndo" @click="$emit('undo')" />
			</el-tooltip>
			<el-tooltip :content="$t('重做 (Ctrl+Shift+Z)')" placement="top">
				<el-button link :icon="RefreshRight" :disabled="!canRedo" @click="$emit('redo')" />
			</el-tooltip>

			<el-button
				type="primary"
				:icon="FolderChecked"
				:loading="saving"
				@click="$emit('save-workflow')"
			>
				{{ $t('保存') }}
			</el-button>

			<el-button type="warning" :icon="Upload" @click="$emit('publish-workflow')">
				{{ $t('发布') }}
			</el-button>

			<el-tooltip :content="runButtonTooltip" placement="top" :disabled="!isTestRunDisabled">
				<div style="display: inline-block; margin-left: 12px">
					<el-button
						type="success"
						:icon="CaretRight"
						class="test-run-btn"
						:disabled="isTestRunDisabled"
						@click="$emit('open-test-dialog')"
					>
						{{ $t('试运行') }}
					</el-button>
				</div>
			</el-tooltip>
		</div>
	</div>
</template>

<script lang="ts" setup>
import { ref, computed, nextTick } from 'vue';
import { useI18n } from 'vue-i18n';
import {
	VideoPlay,
	Cpu,
	Setting,
	Operation,
	UserFilled,
	CircleCheck,
	MagicStick,
	Refresh,
	RefreshLeft,
	RefreshRight,
	Files,
	Picture,
	Collection,
	Filter,
	Search,
	Plus,
	CaretRight,
	Brush,
	Document,
	Download,
	FolderChecked,
	Upload
} from '@element-plus/icons-vue';
import { NODE_REGISTRY } from '../utils/node-type-registry';

const props = defineProps<{
	hasIncompleteNodes?: boolean;
	workflowName: string;
	workflowCode: string;
	testLogDrawerInstanceId: number | null;
	saving: boolean;
	panelOpen?: boolean;
	panelWidth?: number;
	canUndo?: boolean;
	canRedo?: boolean;
}>();

const { t } = useI18n();

const toolbarStyle = computed(() => {
	if (props.panelOpen && props.panelWidth) {
		return { transform: `translateX(calc(-50% - ${props.panelWidth / 2}px))` };
	}
	return {};
});

const nodeSearch = ref('');
const searchInputRef = ref<any>();
const popoverVisible = ref(false);

const categories = computed(() => {
	const cats = [
		{ name: t('基础'), key: 'basic' },
		{ name: t('模型与插件'), key: 'ai' },
		{ name: t('业务逻辑'), key: 'logic' },
		{ name: t('输入与输出'), key: 'system' }
	];

	return cats.map(cat => {
		const items = NODE_REGISTRY.filter(n => {
			if ((n as any).deprecated) return false;
			if (cat.key === 'basic') return n.type === 'start' || n.type === 'end';
			return n.category === cat.key && n.type !== 'start' && n.type !== 'end';
		}).map(n => ({
			type: n.type,
			name: t(n.labelKey),
			desc: n.descKey ? t(n.descKey) : '',
			icon: n.icon
		}));
		return { name: cat.name, items };
	});
});

const filteredCategories = computed(() => {
	const q = nodeSearch.value.trim().toLowerCase();
	if (!q) return categories.value;

	return categories.value.map(cat => {
		return {
			...cat,
			items: cat.items.filter(
				t => t.name.toLowerCase().includes(q) || t.desc.toLowerCase().includes(q)
			)
		};
	});
});

const isSearchEmpty = computed(() => {
	return filteredCategories.value.every(cat => cat.items.length === 0);
});

// 试运行不再被 isDirty 锁死：草稿态下点击会由 openTestDialog/openNodeTestDialog
// 自动保存最新配置后再运行（见 useWorkflowTest/useNodeTest），避免打断"调整→测试→迭代"循环。
// 仅保留"存在未完成配置节点"这一硬阻断（配置缺失确实无法执行）。
const isTestRunDisabled = computed(() => !!props.hasIncompleteNodes);

const runButtonTooltip = computed(() => {
	if (props.hasIncompleteNodes) return t('存在未完成配置的节点，请补充后再试运行');
	return '';
});

const emit = defineEmits([
	'drag-start',
	'add-node',
	'open-test-dialog',
	'clear-test-status',
	'reopen-test-log-drawer',
	'export-workflow',
	'save-workflow',
	'publish-workflow',
	'undo',
	'redo'
]);

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
.editor-bottom-toolbar {
	position: absolute;
	bottom: 24px;
	left: 50%;
	transform: translateX(-50%);
	background: rgba(255, 255, 255, 0.85);
	backdrop-filter: blur(12px);
	border: 1px solid var(--el-border-color-light);
	border-radius: 12px;
	padding: 10px 16px;
	box-shadow: 0 8px 24px rgba(0, 0, 0, 0.08);
	display: flex;
	align-items: center;
	gap: 16px;
	z-index: 5;
	min-width: 300px;
	justify-content: space-between;
}

.toolbar-left,
.toolbar-right {
	display: flex;
	align-items: center;
	gap: 12px;
}

.workflow-title {
	font-size: 14px;
	font-weight: 600;
	color: var(--el-text-color-primary);
}

.add-node-btn {
	border-radius: 8px;
	font-weight: 500;
	padding: 8px 20px;
}

.test-run-btn {
	border-radius: 8px;
	font-weight: 500;
}

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

	// 节点特有左侧边框指示器 (可选，由于采用统一 hover 背景，此处可简化)
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
</style>
<style lang="scss">
// 全局样式覆盖 Popover 的默认 Padding，使其更贴合设计
.node-selector-popover {
	padding: 16px !important;
	border-radius: 12px !important;
	box-shadow: 0 12px 32px rgba(0, 0, 0, 0.1) !important;
}
</style>
