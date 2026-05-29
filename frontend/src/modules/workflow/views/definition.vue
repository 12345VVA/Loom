<template>
	<cl-crud ref="Crud">
		<cl-row>
			<cl-refresh-btn />
			<cl-add-btn />
			<el-button @click="triggerImport" :icon="Upload">{{ $t('导入工作流') }}</el-button>
			<input type="file" ref="fileInput" accept=".json" style="display: none;" @change="handleFileImport" />
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
import { ref } from 'vue';
import { ElMessage } from 'element-plus';
import { Upload } from '@element-plus/icons-vue';

const { service } = useCool();
const { t } = useI18n();
const router = useRouter();
const fileInput = ref<HTMLInputElement | null>(null);
const tempGraphJson = ref('');

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
	],
	onSubmit(data, { next }) {
		if (tempGraphJson.value) {
			data.graphJson = tempGraphJson.value;
			tempGraphJson.value = ''; // clear
		}
		next(data);
	},
	onClosed() {
		tempGraphJson.value = '';
	}
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

function triggerImport() {
	fileInput.value?.click();
}

function handleFileImport(e: Event) {
	const target = e.target as HTMLInputElement;
	if (!target.files || target.files.length === 0) return;
	const file = target.files[0];
	const reader = new FileReader();
	reader.onload = (ev) => {
		try {
			const text = ev.target?.result as string;
			const data = JSON.parse(text);
			if (data.type !== 'LoomWorkflow') {
				ElMessage.error(t('该文件不是有效的 Loom 工作流导出文件'));
				return;
			}
			// 暂存 graphJson 并在提交流程中合并
			tempGraphJson.value = data.graph_json || data.graphJson || '{}';
			// Open Add dialog
			Crud.value?.rowAppend({
				name: data.metadata?.name ? data.metadata.name + ' (导入)' : '导入的工作流',
				description: data.metadata?.description || '',
				status: 1
			});
			ElMessage.success(t('已解析导出文件，请设定唯一编码后保存'));
		} catch (error: any) {
			ElMessage.error(t('文件解析失败：') + error.message);
		} finally {
			// clear input
			target.value = '';
		}
	};
	reader.readAsText(file);
}
</script>

<style lang="scss" scoped>
</style>
