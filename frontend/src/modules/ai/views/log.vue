<template>
	<cl-crud ref="Crud">
		<cl-row>
			<cl-refresh-btn />
			<cl-filter :label="$t('状态')">
				<cl-select :options="statusOptions" prop="status" :width="130" />
			</cl-filter>
			<cl-filter :label="$t('模型类型')">
				<cl-select :options="modelTypeOptions" prop="modelType" :width="130" />
			</cl-filter>
			<cl-flex1 />
			<cl-search-key :placeholder="$t('搜索场景、状态、Request ID、错误')" />
		</cl-row>

		<cl-row>
			<cl-table ref="Table" />
		</cl-row>

		<cl-row>
			<cl-flex1 />
			<cl-pagination />
		</cl-row>
	</cl-crud>
</template>

<script lang="ts" setup>
defineOptions({
	name: 'ai-log'
});

import { useCrud, useTable } from '@cool-vue/crud';
import { useCool } from '/@/cool';
import { useI18n } from 'vue-i18n';

const { service } = useCool();
const { t } = useI18n();

const aiService = service.ai as any;

const statusOptions = [
	{ label: 'success', value: 'success' },
	{ label: 'error', value: 'error' },
	{ label: 'unsupported', value: 'unsupported' }
];

const modelTypeOptions = [
	{ label: 'Chat', value: 'chat' },
	{ label: 'Embedding', value: 'embedding' },
	{ label: 'Image', value: 'image' },
	{ label: 'Audio', value: 'audio' },
	{ label: 'Video', value: 'video' },
	{ label: 'Rerank', value: 'rerank' }
];

const Table = useTable({
	columns: [
		{ label: t('厂商'), prop: 'providerName', minWidth: 140 },
		{ label: t('模型'), prop: 'modelName', minWidth: 150 },
		{ label: t('调用配置'), prop: 'profileName', minWidth: 150 },
		{ label: t('场景'), prop: 'scenario', minWidth: 120 },
		{ label: t('类型'), prop: 'modelType', minWidth: 100 },
		{ label: t('状态'), prop: 'status', minWidth: 110 },
		{ label: t('延迟(ms)'), prop: 'latencyMs', minWidth: 110 },
		{ label: 'Prompt Tokens', prop: 'promptTokens', minWidth: 130 },
		{ label: 'Completion Tokens', prop: 'completionTokens', minWidth: 160 },
		{ label: 'Total Tokens', prop: 'totalTokens', minWidth: 120 },
		{ label: 'Request ID', prop: 'requestId', minWidth: 180, showOverflowTooltip: true },
		{ label: t('错误信息'), prop: 'errorMessage', minWidth: 240, showOverflowTooltip: true },
		{ label: t('创建时间'), prop: 'createTime', sortable: 'desc', minWidth: 170 }
	]
});

const Crud = useCrud(
	{
		service: aiService.log
	},
	app => {
		app.refresh();
	}
);
</script>
