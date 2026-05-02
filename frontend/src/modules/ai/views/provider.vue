<template>
	<cl-crud ref="Crud">
		<cl-row>
			<cl-refresh-btn />
			<cl-add-btn />
			<cl-multi-delete-btn />
			<el-button @click="openCatalog">{{ $t('导入预设') }}</el-button>
			<cl-flex1 />
			<cl-search-key :placeholder="$t('搜索编码、名称')" />
		</cl-row>

		<cl-row>
			<cl-table ref="Table">
				<template #slot-test="{ scope }">
					<el-button text type="primary" @click="testProvider(scope.row)">{{ $t('测试') }}</el-button>
				</template>
			</cl-table>
		</cl-row>

		<cl-row>
			<cl-flex1 />
			<cl-pagination />
		</cl-row>

		<cl-upsert ref="Upsert" />
	</cl-crud>

	<el-drawer v-model="catalog.visible" :title="$t('导入模型厂商预设')" size="520px">
		<el-table :data="catalog.items" border>
			<el-table-column prop="name" :label="$t('厂商')" min-width="140" />
			<el-table-column prop="adapter" :label="$t('适配器')" min-width="150" />
			<el-table-column :label="$t('模型数')" width="90">
				<template #default="{ row }">
					{{ row.models?.length || 0 }}
				</template>
			</el-table-column>
			<el-table-column :label="$t('操作')" width="100">
				<template #default="{ row }">
					<el-button text type="primary" @click="importCatalog(row)">{{ $t('导入') }}</el-button>
				</template>
			</el-table-column>
		</el-table>
	</el-drawer>
</template>

<script lang="ts" setup>
defineOptions({
	name: 'ai-provider'
});

import { useCrud, useTable, useUpsert } from '@cool-vue/crud';
import { ElMessage } from 'element-plus';
import { reactive } from 'vue';
import { useCool } from '/@/cool';
import { useI18n } from 'vue-i18n';

const { service } = useCool();
const { t } = useI18n();

const adapterOptions = [
	{ label: 'OpenAI Compatible', value: 'openai-compatible' },
	{ label: 'Ollama', value: 'ollama' },
	{ label: 'Gemini', value: 'gemini' },
	{ label: 'Claude', value: 'claude' },
	{ label: '火山方舟', value: 'volcengine-ark' },
	{ label: '阿里百炼', value: 'bailian' },
	{ label: '腾讯混元', value: 'hunyuan' },
	{ label: '百度千帆', value: 'qianfan' },
	{ label: '智谱 GLM', value: 'zhipu' },
	{ label: 'MiniMax', value: 'minimax' },
	{ label: '小米 MiMo', value: 'mimo' }
];
const catalog = reactive({
	visible: false,
	items: [] as any[]
});

const Upsert = useUpsert({
	dialog: { width: '760px' },
	props: { labelWidth: '130px' },
	items: [
		{ label: t('编码'), prop: 'code', required: true, component: { name: 'el-input' } },
		{ label: t('名称'), prop: 'name', required: true, component: { name: 'el-input' } },
		{
			label: t('适配器'),
			prop: 'adapter',
			value: 'openai-compatible',
			required: true,
			component: { name: 'cl-select', props: { options: adapterOptions } }
		},
		{ label: 'Base URL', prop: 'baseUrl', component: { name: 'el-input' } },
		{
			label: 'API Key',
			prop: 'apiKey',
			component: {
				name: 'el-input',
				props: {
					type: 'password',
					showPassword: true,
					placeholder: t('留空则不修改已保存密钥')
				}
			}
		},
		{
			label: t('扩展配置'),
			prop: 'extraConfig',
			component: { name: 'el-input', props: { type: 'textarea', rows: 5, placeholder: '{"timeout": 60}' } }
		},
		{ label: t('排序'), prop: 'orderNum', value: 0, component: { name: 'el-input-number' } },
		{ label: t('启用'), prop: 'status', value: true, component: { name: 'el-switch' } }
	],
	onInfo(data, { done }) {
		done({ ...data, apiKey: '' });
	}
});

const Table = useTable({
	columns: [
		{ type: 'selection' },
		{ label: t('编码'), prop: 'code', minWidth: 150 },
		{ label: t('名称'), prop: 'name', minWidth: 150 },
		{ label: t('适配器'), prop: 'adapter', minWidth: 150 },
		{ label: 'Base URL', prop: 'baseUrl', minWidth: 240, showOverflowTooltip: true },
		{ label: 'API Key', prop: 'apiKeyMask', minWidth: 130 },
		{ label: t('启用'), prop: 'status', width: 100 },
		{ label: t('创建时间'), prop: 'createTime', sortable: 'desc', minWidth: 170 },
		{
			type: 'op',
			width: 260,
			buttons: ['edit', 'delete', 'slot-test']
		}
	]
});

const Crud = useCrud(
	{
		service: service.ai.provider
	},
	app => {
		app.refresh();
	}
);

async function openCatalog() {
	catalog.items = await service.ai.provider.catalog({});
	catalog.visible = true;
}

async function importCatalog(row: any) {
	await service.ai.provider.importCatalog({
		providerCode: row.code,
		overwriteModels: true
	});
	ElMessage.success(t('导入成功'));
	Crud.value?.refresh();
}

async function testProvider(row: any) {
	try {
		const res = await service.ai.provider.test({ id: row.id });
		if (res?.success === false) {
			ElMessage.error(res.message || t('连接测试失败'));
			return;
		}
		ElMessage.success(res?.message || t('连接测试成功'));
	} catch (err: any) {
		ElMessage.error(err.message || t('连接测试失败'));
	}
}
</script>
