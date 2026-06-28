<template>
	<cl-crud ref="Crud">
		<cl-row>
			<cl-refresh-btn />
			<cl-add-btn />
			<cl-multi-delete-btn />
			<cl-flex1 />
			<cl-search-key :placeholder="$t('搜索用例结果ID')" />
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
defineOptions({ name: 'workflow-annotation-annotation' });

import { useCrud, useTable, useUpsert } from '@cool-vue/crud';
import { useCool } from '/@/cool';
import { useI18n } from 'vue-i18n';

const { service } = useCool();
const { t } = useI18n();

const Upsert = useUpsert({
	dialog: { width: '560px' },
	props: { labelWidth: '110px' },
	items: [
		{
			label: t('用例结果ID'),
			prop: 'caseResultId',
			required: true,
			component: { name: 'el-input-number', props: { min: 1, controlsPosition: 'right' } }
		},
		{
			label: t('标注'),
			prop: 'label',
			required: true,
			value: 'pass',
			component: {
				name: 'el-select',
				options: [
					{ label: t('通过'), value: 'pass' },
					{ label: t('失败'), value: 'fail' }
				]
			}
		},
		{
			label: t('分数(0-1)'),
			prop: 'score',
			component: { name: 'el-input-number', props: { min: 0, max: 1, step: 0.1, precision: 2 } }
		},
		{
			label: t('理由'),
			prop: 'reason',
			component: { name: 'el-input', props: { type: 'textarea', rows: 3 } }
		},
		{ label: t('金标准'), prop: 'isGold', value: false, component: { name: 'el-switch' } }
	]
});

const Table = useTable({
	columns: [
		{ type: 'selection' },
		{ label: t('用例结果ID'), prop: 'caseResultId', width: 130 },
		{
			label: t('标注'),
			prop: 'label',
			width: 100,
			dict: [
				{ label: t('通过'), value: 'pass', type: 'success' },
				{ label: t('失败'), value: 'fail', type: 'danger' }
			],
			dictColor: true
		},
		{ label: t('分数'), prop: 'score', width: 90 },
		{ label: t('理由'), prop: 'reason', minWidth: 200, showOverflowTooltip: true },
		{ label: t('金标准'), prop: 'isGold', width: 90, component: { name: 'cl-switch' } },
		{ label: t('标注人'), prop: 'annotatorUserId', width: 100 },
		{ label: t('创建时间'), prop: 'createTime', minWidth: 170, sortable: 'desc' },
		{ type: 'op', buttons: ['edit', 'delete'], width: 140 }
	]
});

const Crud = useCrud({ service: (service as any).workflow_annotation.annotation }, app => app.refresh());
</script>

<style lang="scss" scoped></style>
