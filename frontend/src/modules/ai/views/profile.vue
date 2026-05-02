<template>
	<cl-crud ref="Crud">
		<cl-row>
			<cl-refresh-btn />
			<cl-add-btn />
			<cl-multi-delete-btn />
			<cl-flex1 />
			<cl-search-key :placeholder="$t('搜索编码、名称、场景')" />
		</cl-row>

		<cl-row>
			<cl-table ref="Table">
				<template #slot-default="{ scope }">
					<el-button text type="primary" @click="setDefault(scope.row)">{{ $t('设默认') }}</el-button>
				</template>

				<template #slot-test="{ scope }">
					<el-button text type="primary" @click="openTest(scope.row)">{{ $t('测试') }}</el-button>
				</template>
			</cl-table>
		</cl-row>

		<cl-row>
			<cl-flex1 />
			<cl-pagination />
		</cl-row>

		<cl-upsert ref="Upsert" />
	</cl-crud>

	<el-drawer v-model="tester.visible" :title="$t('测试调用')" size="440px">
		<el-form label-position="top">
			<el-form-item :label="$t('提示词')">
				<el-input v-model="tester.prompt" type="textarea" :rows="6" />
			</el-form-item>
			<el-button type="primary" @click="runTest">{{ $t('调用') }}</el-button>
		</el-form>
		<el-input v-if="tester.result" v-model="tester.result" type="textarea" :rows="12" class="result" />
	</el-drawer>
</template>

<script lang="ts" setup>
defineOptions({
	name: 'ai-profile'
});

import { useCrud, useTable, useUpsert } from '@cool-vue/crud';
import { ElMessage } from 'element-plus';
import { reactive } from 'vue';
import { useCool } from '/@/cool';
import { useI18n } from 'vue-i18n';

const { service } = useCool();
const { t } = useI18n();

const tester = reactive({
	visible: false,
	id: 0,
	prompt: '你好，请用一句话介绍你自己。',
	result: ''
});

const Upsert = useUpsert({
	dialog: { width: '860px' },
	props: { labelWidth: '140px' },
	items: [
		{ label: t('编码'), prop: 'code', required: true, component: { name: 'el-input' } },
		{ label: t('名称'), prop: 'name', required: true, component: { name: 'el-input' } },
		{
			label: t('模型'),
			prop: 'modelId',
			required: true,
			component: {
				name: 'cl-select-table',
				props: {
					service: service.ai.model,
					columns: [
						{ label: t('厂商'), prop: 'providerName', minWidth: 140 },
						{ label: t('编码'), prop: 'code', minWidth: 160 },
						{ label: t('类型'), prop: 'modelType', minWidth: 110 }
					]
				}
			}
		},
		{ label: t('场景'), prop: 'scenario', value: 'default', required: true, component: { name: 'el-input' } },
		{ label: 'temperature', prop: 'temperature', component: { name: 'el-input-number', props: { min: 0, max: 2, step: 0.1 } } },
		{ label: 'top_p', prop: 'topP', component: { name: 'el-input-number', props: { min: 0, max: 1, step: 0.05 } } },
		{ label: 'max_tokens', prop: 'maxTokens', component: { name: 'el-input-number' } },
		{
			label: 'response_format',
			prop: 'responseFormat',
			component: { name: 'el-input', props: { type: 'textarea', rows: 3, placeholder: '{"type": "json_object"}' } }
		},
		{
			label: 'tools',
			prop: 'toolsConfig',
			component: { name: 'el-input', props: { type: 'textarea', rows: 4, placeholder: '[]' } }
		},
		{
			label: t('兜底配置ID'),
			prop: 'fallbackProfileId',
			component: { name: 'el-input-number' }
		},
		{ label: t('默认'), prop: 'isDefault', value: false, component: { name: 'el-switch' } },
		{ label: t('排序'), prop: 'orderNum', value: 0, component: { name: 'el-input-number' } },
		{ label: t('启用'), prop: 'status', value: true, component: { name: 'el-switch' } }
	]
});

const Table = useTable({
	columns: [
		{ type: 'selection' },
		{ label: t('编码'), prop: 'code', minWidth: 160 },
		{ label: t('名称'), prop: 'name', minWidth: 150 },
		{ label: t('场景'), prop: 'scenario', minWidth: 130 },
		{ label: t('模型'), prop: 'modelName', minWidth: 160 },
		{ label: t('类型'), prop: 'modelType', minWidth: 110 },
		{ label: t('厂商'), prop: 'providerName', minWidth: 140 },
		{ label: t('默认'), prop: 'isDefault', width: 90 },
		{ label: t('启用'), prop: 'status', width: 90 },
		{ label: t('创建时间'), prop: 'createTime', sortable: 'desc', minWidth: 170 },
		{
			type: 'op',
			width: 310,
			buttons: ['edit', 'delete', 'slot-default', 'slot-test']
		}
	]
});

const Crud = useCrud(
	{
		service: service.ai.profile
	},
	app => {
		app.refresh();
	}
);

async function setDefault(row: any) {
	await service.ai.profile.setDefault({ id: row.id });
	ElMessage.success(t('设置成功'));
	Crud.value?.refresh();
}

function openTest(row: any) {
	tester.id = row.id;
	tester.result = '';
	tester.visible = true;
}

async function runTest() {
	try {
		const res = await service.ai.profile.test({ id: tester.id, prompt: tester.prompt });
		tester.result = JSON.stringify(res, null, 2);
	} catch (err: any) {
		ElMessage.error(err.message || t('调用失败'));
	}
}
</script>

<style lang="scss" scoped>
.result {
	margin-top: 16px;
}
</style>
