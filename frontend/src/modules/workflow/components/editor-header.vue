<template>
	<div class="editor-header">
		<div class="editor-header__left">
			<el-button :icon="ArrowLeft" circle @click="$emit('go-back')" />
			<span class="workflow-title">{{ workflowName || $t('未命名工作流') }}</span>
			<el-tag size="small" type="info" class="workflow-code">{{ workflowCode }}</el-tag>
		</div>
		<div class="editor-header__right">
			<template v-if="testLogDrawerInstanceId">
				<el-button plain type="info" @click="$emit('clear-test-status')">
					<el-icon><brush /></el-icon>{{ $t('清除状态') }}
				</el-button>
				<el-button plain type="primary" @click="$emit('reopen-test-log-drawer')">
					<el-icon><document /></el-icon>{{ $t('测试日志') }}
				</el-button>
			</template>

			<el-button @click="$emit('export-workflow')" :icon="Download">
				{{ $t('导出工作流') }}
			</el-button>
			<el-button
				type="primary"
				:icon="FolderChecked"
				:loading="saving"
				@click="$emit('save-workflow')"
			>
				{{ $t('保存工作流') }}
			</el-button>
		</div>
	</div>
</template>

<script lang="ts" setup>
import { useI18n } from 'vue-i18n';
import { ArrowLeft, Brush, Document, Download, FolderChecked } from '@element-plus/icons-vue';

const { t } = useI18n();

defineProps<{
	workflowName: string;
	workflowCode: string;
	testLogDrawerInstanceId: number | null;
	saving: boolean;
}>();

defineEmits([
	'go-back',
	'clear-test-status',
	'reopen-test-log-drawer',
	'export-workflow',
	'save-workflow'
]);
</script>

<style lang="scss" scoped>
.editor-header {
	display: flex;
	align-items: center;
	justify-content: space-between;
	height: 60px;
	padding: 0 20px;
	background-color: #fff;
	border-bottom: 1px solid var(--el-border-color-light);
	box-shadow: 0 2px 4px rgba(0, 0, 0, 0.02);
	z-index: 2;

	&__left {
		display: flex;
		align-items: center;
		gap: 12px;

		.workflow-title {
			font-size: 16px;
			font-weight: 600;
			color: var(--el-text-color-primary);
		}
	}

	&__right {
		display: flex;
		align-items: center;
		gap: 8px;
	}
}
</style>
