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
			<el-tag v-if="showHint" class="capability-hint" type="info" effect="plain">
				{{ $t('能力字段是模型元信息，未实现接口仍会返回 501。') }}
			</el-tag>
			<el-button text type="primary" @click="showHint = !showHint">
				{{ showHint ? $t('隐藏说明') : $t('说明') }}
			</el-button>
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
import { ref } from 'vue';
import { useI18n } from 'vue-i18n';

const { service } = useCool();
const { t } = useI18n();
const showHint = ref(false);

const modelTypeOptions = [
	{ label: t('对话'), value: 'chat' },
	{ label: t('向量'), value: 'embedding' },
	{ label: t('图片'), value: 'image' },
	{ label: t('音频'), value: 'audio' },
	{ label: t('视频'), value: 'video' },
	{ label: t('重排'), value: 'rerank' }
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
					multiple: false,
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
		{ label: t('类型'), prop: 'modelType', minWidth: 120, formatter: ({ modelType }: any) => optionLabel(modelTypeOptions, modelType) },
		{
			label: t('能力'),
			prop: 'capabilities',
			minWidth: 220,
			showOverflowTooltip: true,
			formatter: ({ capabilities }: any) => splitCapabilities(capabilities).join(' / ') || '-'
		},
		{ label: t('上下文'), prop: 'contextWindow', minWidth: 110 },
		{ label: t('最大输出'), prop: 'maxOutputTokens', minWidth: 110 },
		{ label: t('启用'), prop: 'status', width: 100 },
		{ label: t('创建时间'), prop: 'createTime', sortable: 'desc', minWidth: 170 },
		{ type: 'op', buttons: ['edit', 'delete'] }
	]
});

const Crud = useCrud(
	{
		service: service.ai.model
	},
	app => {
		app.refresh();
	}
);

function splitCapabilities(value?: string) {
	return String(value || '')
		.split(',')
		.map(item => item.trim())
		.filter(Boolean);
}

function optionLabel(options: { label: string; value: string }[], value: string) {
	return options.find(item => item.value === value)?.label || value || '-';
}
</script>

<style lang="scss" scoped>
.capability-hint {
	max-width: 520px;
	overflow: hidden;
	text-overflow: ellipsis;
	white-space: nowrap;
}

</style>
