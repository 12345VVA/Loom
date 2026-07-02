<template>
	<cl-crud ref="Crud">
		<cl-row>
			<cl-refresh-btn />
			<cl-add-btn />
			<cl-multi-delete-btn />
			<cl-flex1 />
			<cl-search-key :placeholder="$t('搜索名称')" />
		</cl-row>

		<cl-row>
			<cl-table ref="Table">
				<template #slot-import="{ scope }">
					<el-button text type="primary" @click="triggerImport(scope.row)">{{
						$t('导入用例')
					}}</el-button>
				</template>
			</cl-table>
		</cl-row>

		<cl-row>
			<cl-flex1 />
			<cl-pagination />
		</cl-row>

		<cl-upsert ref="Upsert" />
	</cl-crud>

	<input ref="fileInput" type="file" accept=".json" style="display: none" @change="handleImport" />
</template>

<script lang="ts" setup>
defineOptions({ name: 'workflow-eval-suite' });

import { useCrud, useTable, useUpsert } from '@cool-vue/crud';
import { ElMessage } from 'element-plus';
import { ref } from 'vue';
import { useCool } from '/@/cool';
import { useI18n } from 'vue-i18n';

const { service } = useCool();
const { t } = useI18n();
const evalService = (service as any).workflow_eval;

const definitionOptions = ref<{ label: string; value: number }[]>([]);
(async () => {
	try {
		const res = await (service as any).workflow.definition.list();
		definitionOptions.value = (res || []).map((d: any) => ({
			label: d.name || `#${d.id}`,
			value: d.id
		}));
	} catch (e) {
		// ignore
		console.warn('[workflow_eval/suite] 拉取 workflow.definition.list 失败', e);
	}
})();

const Crud = useCrud({ service: evalService.test_set }, (app) => app.refresh());

const Table = useTable({
	columns: [
		{ type: 'selection' },
		{ label: t('名称'), prop: 'name', minWidth: 160 },
		{ label: t('描述'), prop: 'description', minWidth: 200, showOverflowTooltip: true },
		{ label: t('用例数'), prop: 'itemsCount', width: 90 },
		{ label: t('标签'), prop: 'tags', minWidth: 120, showOverflowTooltip: true },
		{ label: t('创建时间'), prop: 'createTime', minWidth: 170, sortable: 'desc' },
		{ type: 'op', buttons: ['edit', 'delete', 'slot-import'], width: 220 }
	]
});

const Upsert = useUpsert({
	dialog: { width: '600px' },
	items: [
		{ label: t('名称'), prop: 'name', required: true, component: { name: 'el-input' } },
		{
			label: t('描述'),
			prop: 'description',
			component: { name: 'el-input', props: { type: 'textarea' } }
		},
		{
			label: t('关联工作流'),
			prop: 'definitionId',
			component: {
				name: 'el-select',
				props: { clearable: true, filterable: true },
				options: definitionOptions
			}
		},
		{
			label: t('标签'),
			prop: 'tags',
			component: { name: 'el-input', props: { placeholder: t('逗号分隔') } }
		}
	]
});

// 用例导入
const fileInput = ref<HTMLInputElement | null>(null);
const importTestSetId = ref<number | null>(null);

function triggerImport(row: any) {
	importTestSetId.value = row.id;
	fileInput.value?.click();
}

async function handleImport(e: Event) {
	const target = e.target as HTMLInputElement;
	const file = target.files?.[0];
	const testSetId = importTestSetId.value;
	if (!file || !testSetId) return;
	try {
		const text = await file.text();
		const cases = JSON.parse(text);
		if (!Array.isArray(cases)) throw new Error('JSON 必须是数组');
		const res = await evalService.test_set.importCases({ testSetId, cases });
		ElMessage.success(`${t('已导入')} ${res.imported} ${t('条')}`);
		Crud.value?.refresh();
	} catch (err: any) {
		ElMessage.error(`${t('导入失败')}: ${err.message || err}`);
	} finally {
		target.value = '';
		importTestSetId.value = null;
	}
}
</script>
