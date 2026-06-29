<template>
	<cl-crud ref="Crud">
		<cl-row>
			<cl-refresh-btn />
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
	</cl-crud>
</template>

<script lang="ts" setup>
defineOptions({ name: 'workflow-annotation-annotation' });

import { useCrud, useTable } from '@cool-vue/crud';
import { useCool } from '/@/cool';
import { useI18n } from 'vue-i18n';

const { service } = useCool();
const { t } = useI18n();

// 只读历史流水页：标注入口已迁移至「评估运行详情」抽屉（annotation-drawer），此处仅作审计查阅
const Table = useTable({
	columns: [
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
		{
			label: t('金标准'),
			prop: 'isGold',
			width: 90,
			dict: [
				{ label: t('是'), value: true, type: 'warning' },
				{ label: t('否'), value: false }
			],
			dictColor: true
		},
		{ label: t('标注人'), prop: 'annotatorUserId', width: 100 },
		{ label: t('创建时间'), prop: 'createTime', minWidth: 170, sortable: 'desc' }
	]
});

const Crud = useCrud({ service: (service as any).workflow_annotation.annotation }, app => app.refresh());
</script>

<style lang="scss" scoped></style>
