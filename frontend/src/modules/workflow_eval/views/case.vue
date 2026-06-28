<template>
	<cl-crud ref="Crud">
		<cl-row>
			<el-select
				v-model="testSetId"
				:placeholder="$t('选择测试集筛选')"
				filterable
				clearable
				style="width: 240px"
				@change="onTestSetChange"
			>
				<el-option
					v-for="ts in testSetOptions"
					:key="ts.id"
					:label="`${ts.name} (${ts.itemsCount}例)`"
					:value="ts.id"
				/>
			</el-select>
			<cl-refresh-btn />
			<cl-add-btn />
			<cl-multi-delete-btn />
			<cl-flex1 />
			<cl-search-key :placeholder="$t('搜索 case_key')" />
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
defineOptions({ name: 'workflow-eval-case' });

import { useCrud, useTable, useUpsert } from '@cool-vue/crud';
import { ref } from 'vue';
import { useCool } from '/@/cool';
import { useI18n } from 'vue-i18n';

const { service } = useCool();
const { t } = useI18n();
const evalService = (service as any).workflow_eval;

// 测试集选项（顶部筛选 + 新增表单共用）
const testSetOptions = ref<any[]>([]);
const testSetId = ref<any>(null);
(async () => {
	try {
		const res = await evalService.test_set.list();
		testSetOptions.value = res || [];
	} catch (e) {
		// ignore
	}
})();

const Crud = useCrud({ service: evalService.test_case }, (app) => app.refresh());

function onTestSetChange() {
	Crud.value?.refresh({ testSetId: testSetId.value });
}

const Table = useTable({
	columns: [
		{ type: 'selection' },
		{ label: 'case_key', prop: 'caseKey', minWidth: 140 },
		{ label: t('输入(JSON)'), prop: 'inputData', minWidth: 220, showOverflowTooltip: true },
		{ label: t('期望文本'), prop: 'expectedText', minWidth: 160, showOverflowTooltip: true },
		{ label: t('评估器配置'), prop: 'evaluatorConfig', minWidth: 200, showOverflowTooltip: true },
		{ label: t('权重'), prop: 'weight', width: 80 },
		{ label: t('排序'), prop: 'sortOrder', width: 80 },
		{ type: 'op', buttons: ['edit', 'delete'], width: 140 }
	]
});

// JSON 字段合法性校验（input_data / expected_output / evaluator_config）
function jsonRule(label: string) {
	return {
		validator: (_r: any, v: any, cb: any) => {
			if (v === null || v === undefined || v === '') return cb();
			try {
				JSON.parse(v);
				cb();
			} catch {
				cb(new Error(`${label} ${t('不是合法 JSON')}`));
			}
		},
		trigger: 'blur'
	};
}

const EVAL_CONFIG_PLACEHOLDER = [
	t('规则匹配') + ': {"mode":"contains","tolerance":0}',
	t('LLM评分') + ': {"judge_profile_code":"profile-code","threshold":0.6,"judge_prompt":"..."}',
	t('组合') + ': {"children":[{"type":"rule_match","config":{"mode":"contains","expected_text":"ok"},"weight":1}]}'
].join('\n');

const Upsert = useUpsert({
	dialog: { width: '680px' },
	onOpen: ((data: any, { next }: any) => {
		// 新增时默认带入顶部筛选的测试集
		if (!data?.id && testSetId.value) {
			next({ ...data, testSetId: testSetId.value });
		} else {
			next();
		}
	}) as any,
	items: [
		() => ({
			label: t('测试集'),
			prop: 'testSetId',
			required: true,
			component: {
				name: 'el-select',
				props: { filterable: true },
				options: testSetOptions
			},
			hidden: Upsert.value?.mode === 'update'
		}),
		{ label: 'case_key', prop: 'caseKey', required: true, component: { name: 'el-input' } },
		{
			label: t('输入(JSON)'),
			prop: 'inputData',
			component: { name: 'el-input', props: { type: 'textarea', rows: 4 } },
			rules: [jsonRule(t('输入'))]
		},
		{
			label: t('期望输出(JSON)'),
			prop: 'expectedOutput',
			component: { name: 'el-input', props: { type: 'textarea', rows: 3 } },
			rules: [jsonRule(t('期望输出'))]
		},
		{
			label: t('期望文本'),
			prop: 'expectedText',
			component: { name: 'el-input', props: { type: 'textarea', rows: 2 } }
		},
		{
			label: t('评估器配置(JSON)'),
			prop: 'evaluatorConfig',
			component: {
				name: 'el-input',
				props: { type: 'textarea', rows: 4, placeholder: EVAL_CONFIG_PLACEHOLDER }
			},
			rules: [jsonRule(t('评估器配置'))]
		},
		{
			label: t('权重'),
			prop: 'weight',
			component: { name: 'el-input-number', props: { min: 0, step: 0.1 } }
		},
		{
			label: t('排序'),
			prop: 'sortOrder',
			component: { name: 'el-input-number', props: { min: 0 } }
		}
	]
});
</script>
