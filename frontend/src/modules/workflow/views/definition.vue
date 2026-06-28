<template>
	<cl-crud ref="Crud">
		<cl-row>
			<cl-refresh-btn />
			<cl-add-btn />
			<el-button @click="triggerImport" :icon="Upload">{{ $t('导入工作流') }}</el-button>
			<input
				type="file"
				ref="fileInput"
				accept=".json"
				style="display: none"
				@change="handleFileImport"
			/>
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
				<template #slot-publish="{ scope }">
					<el-button
						text
						type="success"
						:disabled="!scope.row.draftVersionId"
						@click="publishDraft(scope.row)"
					>{{ $t('发布') }}</el-button>
				</template>
				<template #slot-version="{ scope }">
					<el-button text type="primary" @click="versionHistory(scope.row)">
						{{ $t('版本') }}
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
import { ElMessage, ElMessageBox } from 'element-plus';
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
		{
			label: t('启用'),
			prop: 'status',
			value: 1,
			component: { name: 'el-switch', props: { activeValue: 1, inactiveValue: 0 } }
		}
	],
	async onSubmit(data, { next }) {
		// 导入的拓扑暂存：definition 创建后存为草稿（纯版本表模型：graph 不在主表）
		const graphJson = tempGraphJson.value;
		tempGraphJson.value = '';
		const res: any = await next(data);
		if (graphJson && res?.id) {
			try {
				await (service as any).workflow.definition.saveDraft({
					definitionId: res.id,
					graphJson
				});
			} catch (e: any) {
				ElMessage.warning(t('拓扑草稿保存失败：') + (e?.message || e));
			}
		}
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
		{ label: t('当前版本'), prop: 'currentVersionNo', width: 100 },
		{ label: t('发布时间'), prop: 'currentPublishedAt', minWidth: 170 },
		{ label: t('创建时间'), prop: 'createTime', sortable: 'desc', minWidth: 170 },
		{
			type: 'op',
			width: 480,
			buttons: ['edit', 'delete', 'slot-design', 'slot-publish', 'slot-version']
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

// 发布当前草稿（草稿→发布一步上线；运行中实例按其版本继续跑，不受影响）
async function publishDraft(row: any) {
	try {
		await ElMessageBox.confirm(
			t('确认发布当前草稿？发布后新启动的实例将使用此版本，正在运行的实例不受影响。'),
			t('提示'),
			{ type: 'warning' }
		);
		await (service as any).workflow.version.publish({ definitionId: row.id });
		ElMessage.success(t('发布成功'));
		Crud.value?.refresh();
	} catch (e: any) {
		if (e !== 'cancel') ElMessage.error(t('发布失败：') + (e?.message || e));
	}
}

// 跳转版本历史页（版本列表 / 对比 / 回滚）
function versionHistory(scope: WorkflowDefinition) {
	router.push({ path: '/workflow/version', query: { definitionId: scope.id } });
}

function triggerImport() {
	fileInput.value?.click();
}

function handleFileImport(e: Event) {
	const target = e.target as HTMLInputElement;
	if (!target.files || target.files.length === 0) return;
	const file = target.files[0];
	const reader = new FileReader();
	reader.onload = ev => {
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

<style lang="scss" scoped></style>
