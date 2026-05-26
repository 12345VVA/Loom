<template>
	<cl-crud ref="Crud">
		<cl-row>
			<cl-refresh-btn />
			<cl-add-btn />
			<cl-multi-delete-btn />
			<cl-flex1 />
			<cl-search-key :placeholder="$t('搜索编码、名称')" />
		</cl-row>

		<cl-row>
			<cl-table ref="Table">
				<template #slot-design="{ scope }">
					<el-button text type="primary" @click="designWorkflow(scope.row)">
						{{ $t('设计工作流') }}
					</el-button>
				</template>
			</cl-table>
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
	name: 'workflow-definition'
});

import { useCrud, useTable, useUpsert } from '@cool-vue/crud';
import { useCool } from '/@/cool';
import { useRouter } from 'vue-router';
import { useI18n } from 'vue-i18n';

const { service } = useCool();
const { t } = useI18n();
const router = useRouter();

const Upsert = useUpsert({
	dialog: { width: '600px' },
	props: { labelWidth: '100px' },
	items: [
		{ label: t('工作流编码'), prop: 'code', required: true, component: { name: 'el-input' } },
		{ label: t('工作流名称'), prop: 'name', required: true, component: { name: 'el-input' } },
		{
			label: t('描述'),
			prop: 'description',
			component: { name: 'el-input', props: { type: 'textarea', rows: 4 } }
		},
		{ label: t('启用'), prop: 'status', value: 1, component: { name: 'el-switch', props: { activeValue: 1, inactiveValue: 0 } } }
	]
});

const Table = useTable({
	columns: [
		{ type: 'selection' },
		{ label: t('工作流编码'), prop: 'code', minWidth: 160 },
		{ label: t('工作流名称'), prop: 'name', minWidth: 180 },
		{ label: t('描述'), prop: 'description', minWidth: 260, showOverflowTooltip: true },
		{ label: t('启用'), prop: 'status', width: 100, component: { name: 'cl-switch' } },
		{ label: t('创建时间'), prop: 'createTime', sortable: 'desc', minWidth: 170 },
		{
			type: 'op',
			width: 320,
			buttons: ['edit', 'delete', 'slot-design']
		}
	]
});

const Crud = useCrud(
	{
		service: (service as any).workflow.definition
	},
	app => {
		app.refresh();
	}
);

interface WorkflowDefinition {
	id: number;
	code: string;
	name: string;
	description?: string;
	graphJson?: string;
	status: number;
	createTime: string;
	updateTime: string;
}

// 前往 Vue Flow 可视化连线设计器页面
function designWorkflow(scope: WorkflowDefinition) {
	router.push({
		path: '/workflow/editor',
		query: { id: scope.id }
	});
}
</script>

<style lang="scss" scoped>
</style>
