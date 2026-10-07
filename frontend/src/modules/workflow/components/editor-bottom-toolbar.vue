<template>
	<div class="editor-bottom-toolbar" @contextmenu.prevent :style="toolbarStyle">
		<div class="toolbar-left">
			<span class="workflow-title">{{ workflowName || $t('未命名工作流') }}</span>
			<el-tag size="small" type="info" class="workflow-code">{{ workflowCode }}</el-tag>
		</div>

		<div class="toolbar-right">
			<template v-if="testLogDrawerInstanceId">
				<el-button plain type="info" @click="$emit('clear-test-status')">
					<el-icon><Brush /></el-icon>{{ $t('清除') }}
				</el-button>
				<el-button plain type="primary" @click="$emit('reopen-test-log-drawer')">
					<el-icon><Document /></el-icon>{{ $t('日志') }}
				</el-button>
				<el-divider direction="vertical" style="margin: 0 8px" />
			</template>

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
				<div style="display: inline-block; margin-left: 8px">
					<el-button
						type="success"
						:icon="CaretRight"
						class="test-run-btn"
						:disabled="isTestRunDisabled"
						@click="$emit('open-test-dialog')"
					>
						{{ $t('试运行（草稿）') }}
					</el-button>
				</div>
			</el-tooltip>
		</div>
	</div>
</template>

<script lang="ts" setup>
import { computed } from 'vue';
import { useI18n } from 'vue-i18n';
import {
	CaretRight,
	Brush,
	Document,
	FolderChecked,
	Upload
} from '@element-plus/icons-vue';

const props = defineProps<{
	hasIncompleteNodes?: boolean;
	workflowName: string;
	workflowCode: string;
	testLogDrawerInstanceId: number | null;
	saving: boolean;
	panelOpen?: boolean;
	panelWidth?: number;
}>();

const { t } = useI18n();

const toolbarStyle = computed(() => {
	if (props.panelOpen && props.panelWidth) {
		return { transform: `translateX(calc(-50% - ${props.panelWidth / 2}px))` };
	}
	return {};
});

const isTestRunDisabled = computed(() => !!props.hasIncompleteNodes);

const runButtonTooltip = computed(() => {
	if (props.hasIncompleteNodes) return t('存在未完成配置的节点，请补充后再试运行');
	return '';
});

defineEmits([
	'open-test-dialog',
	'clear-test-status',
	'reopen-test-log-drawer',
	'save-workflow',
	'publish-workflow'
]);
</script>

<style lang="scss" scoped>
.editor-bottom-toolbar {
	position: absolute;
	bottom: 24px;
	left: 50%;
	transform: translateX(-50%);
	transition: transform 0.25s ease;
	background: rgba(255, 255, 255, 0.88);
	backdrop-filter: blur(12px);
	border: 1px solid var(--el-border-color-light);
	border-radius: 12px;
	padding: 8px 16px;
	box-shadow: 0 8px 24px rgba(0, 0, 0, 0.08);
	display: flex;
	align-items: center;
	gap: 16px;
	z-index: 5;
	justify-content: space-between;
}

.toolbar-left,
.toolbar-right {
	display: flex;
	align-items: center;
	gap: 10px;
}

.workflow-title {
	font-size: 14px;
	font-weight: 600;
	color: var(--el-text-color-primary);
	max-width: 220px;
	overflow: hidden;
	text-overflow: ellipsis;
	white-space: nowrap;
}

.test-run-btn {
	border-radius: 8px;
	font-weight: 500;
}
</style>
