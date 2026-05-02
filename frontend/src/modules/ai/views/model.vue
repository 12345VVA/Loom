<template>
	<cl-crud ref="Crud">
		<cl-row>
			<cl-refresh-btn />
			<cl-add-btn />
			<cl-multi-delete-btn />
			<cl-filter :label="$t('模型类型')">
				<cl-select :options="modelTypeOptions" prop="modelType" :width="130" />
			</cl-filter>
			<cl-flex1 />
			<cl-search-key :placeholder="$t('搜索编码、名称')" />
		</cl-row>

		<cl-row>
			<cl-table ref="Table" />
		</cl-row>

		<cl-row>
			<cl-flex1 />
			<cl-pagination />
		</cl-row>

		<cl-upsert ref="Upsert" />
	</cl-crud>
</template>

<script lang="ts" setup>
defineOptions({
	name: 'ai-model'
});

import { useCrud, useTable, useUpsert } from '@cool-vue/crud';
import { useCool } from '/@/cool';
import { useI18n } from 'vue-i18n';

const { service } = useCool();
const { t } = useI18n();

const modelTypeOptions = [
	{ label: 'Chat', value: 'chat' },
	{ label: 'Embedding', value: 'embedding' },
	{ label: 'Image', value: 'image' },
	{ label: 'Audio', value: 'audio' },
	{ label: 'Video', value: 'video' },
	{ label: 'Rerank', value: 'rerank' }
];

const Upsert = useUpsert({
	dialog: { width: '820px' },
	props: { labelWidth: '140px' },
	items: [
		{
			label: t('厂商'),
			prop: 'providerId',
			required: true,
			component: {
				name: 'cl-select-table',
				props: {
					service: service.ai.provider,
					columns: [
						{ label: t('编码'), prop: 'code', minWidth: 140 },
						{ label: t('名称'), prop: 'name', minWidth: 140 },
						{ label: t('适配器'), prop: 'adapter', minWidth: 140 }
					]
				}
			}
		},
		{ label: t('编码'), prop: 'code', required: true, component: { name: 'el-input' } },
		{ label: t('名称'), prop: 'name', required: true, component: { name: 'el-input' } },
		{
			label: t('模型类型'),
			prop: 'modelType',
			value: 'chat',
			required: true,
			component: { name: 'cl-select', props: { options: modelTypeOptions } }
		},
		{ label: t('能力'), prop: 'capabilities', component: { name: 'el-input', props: { placeholder: 'vision,json,tool' } } },
		{ label: t('上下文长度'), prop: 'contextWindow', component: { name: 'el-input-number' } },
		{ label: t('最大输出'), prop: 'maxOutputTokens', component: { name: 'el-input-number' } },
		{
			label: t('价格配置'),
			prop: 'pricingConfig',
			component: { name: 'el-input', props: { type: 'textarea', rows: 4, placeholder: '{"input": 0, "output": 0}' } }
		},
		{
			label: t('默认参数'),
			prop: 'defaultConfig',
			component: { name: 'el-input', props: { type: 'textarea', rows: 5, placeholder: '{"temperature": 0.7}' } }
		},
		{ label: t('排序'), prop: 'orderNum', value: 0, component: { name: 'el-input-number' } },
		{ label: t('启用'), prop: 'status', value: true, component: { name: 'el-switch' } }
	]
});

const Table = useTable({
	columns: [
		{ type: 'selection' },
		{ label: t('厂商'), prop: 'providerName', minWidth: 150 },
		{ label: t('编码'), prop: 'code', minWidth: 180 },
		{ label: t('名称'), prop: 'name', minWidth: 160 },
		{ label: t('类型'), prop: 'modelType', minWidth: 120 },
		{ label: t('上下文'), prop: 'contextWindow', minWidth: 110 },
		{ label: t('最大输出'), prop: 'maxOutputTokens', minWidth: 110 },
		{ label: t('启用'), prop: 'status', width: 100 },
		{ label: t('创建时间'), prop: 'createTime', sortable: 'desc', minWidth: 170 },
		{ type: 'op', buttons: ['edit', 'delete'] }
	]
});

useCrud(
	{
		service: service.ai.model
	},
	app => {
		app.refresh();
	}
);
</script>
