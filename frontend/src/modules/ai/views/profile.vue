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

	<cl-upsert ref="Upsert">
		<template #slot-response-format="{ scope }">
			<div class="response-format">
				<el-segmented v-model="scope.responseFormatMode" :options="responseFormatModes" />
				<el-alert
					class="mt-2"
					title="OpenAI Compatible、DeepSeek、百炼、火山方舟、混元、千帆、智谱、MiniMax 等兼容适配器会透传 response_format；Claude、Gemini、Ollama 暂不做协议转换，可能由上游拒绝或忽略。"
					type="info"
					show-icon
					:closable="false"
				/>
				<template v-if="scope.responseFormatMode === 'json_schema'">
					<el-input v-model="scope.responseSchemaName" class="mt-2" placeholder="schema_name" />
					<el-input v-model="scope.responseSchemaDescription" class="mt-2" placeholder="description" />
					<el-switch v-model="scope.responseSchemaStrict" class="mt-2" active-text="strict" />
					<el-input
						v-model="scope.responseSchemaBody"
						class="mt-2"
						type="textarea"
						:rows="8"
						placeholder='{"type":"object","properties":{},"required":[],"additionalProperties":false}'
					/>
				</template>
			</div>
		</template>
	</cl-upsert>
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

const responseFormatModes = [
	{ label: 'Text', value: 'text' },
	{ label: 'JSON Object', value: 'json_object' },
	{ label: 'JSON Schema', value: 'json_schema' }
];

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
					multiple: false,
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
			prop: 'responseFormatMode',
			value: 'text',
			component: { name: 'slot-response-format' }
		},
		{
			label: 'tools',
			prop: 'toolsConfig',
			component: { name: 'el-input', props: { type: 'textarea', rows: 4, placeholder: '[]' } }
		},
		{
			label: 'timeout(s)',
			prop: 'timeout',
			component: { name: 'el-input-number', props: { min: 1, 'controls-position': 'right' } }
		},
		{
			label: 'retry_count',
			prop: 'retryCount',
			value: 0,
			component: { name: 'el-input-number', props: { min: 0, max: 5, 'controls-position': 'right' } }
		},
		{
			label: 'retry_delay(s)',
			prop: 'retryDelaySeconds',
			value: 0,
			component: { name: 'el-input-number', props: { min: 0, max: 60, 'controls-position': 'right' } }
		},
		{
			label: t('兜底配置ID'),
			prop: 'fallbackProfileId',
			component: { name: 'el-input-number' }
		},
		{ label: t('默认'), prop: 'isDefault', value: false, component: { name: 'el-switch' } },
		{ label: t('排序'), prop: 'orderNum', value: 0, component: { name: 'el-input-number' } },
		{ label: t('启用'), prop: 'status', value: true, component: { name: 'el-switch' } }
	],
	onInfo(data, { done }) {
		service.ai.profile.info({ id: data.id }).then((res: any) => {
			done({ ...res, ...parseResponseFormat(res.responseFormat) });
		});
	},
	onSubmit(data, { next, done }) {
		try {
			const payload = { ...data, modelId: normalizeSingleId(data.modelId), responseFormat: stringifyResponseFormat(data) };
			delete payload.responseFormatMode;
			delete payload.responseSchemaName;
			delete payload.responseSchemaDescription;
			delete payload.responseSchemaStrict;
			delete payload.responseSchemaBody;
			next(payload);
		} catch (err: any) {
			ElMessage.error(err.message || t('保存失败'));
			done();
		}
	}
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

function parseResponseFormat(value?: string) {
	const defaults = {
		responseFormatMode: 'text',
		responseSchemaName: '',
		responseSchemaDescription: '',
		responseSchemaStrict: true,
		responseSchemaBody: '{\n  "type": "object",\n  "properties": {},\n  "required": [],\n  "additionalProperties": false\n}'
	};
	if (!value) {
		return defaults;
	}
	try {
		const data = JSON.parse(value);
		if (data?.type === 'json_object') {
			return { ...defaults, responseFormatMode: 'json_object' };
		}
		if (data?.type === 'json_schema') {
			const jsonSchema = data.json_schema || data.jsonSchema || {};
			return {
				...defaults,
				responseFormatMode: 'json_schema',
				responseSchemaName: jsonSchema.name || '',
				responseSchemaDescription: jsonSchema.description || '',
				responseSchemaStrict: jsonSchema.strict !== false,
				responseSchemaBody: JSON.stringify(jsonSchema.schema || {}, null, 2)
			};
		}
		return defaults;
	} catch {
		return defaults;
	}
}

function stringifyResponseFormat(data: any) {
	if (!data.responseFormatMode || data.responseFormatMode === 'text') {
		return undefined;
	}
	if (data.responseFormatMode === 'json_object') {
		return JSON.stringify({ type: 'json_object' });
	}
	const name = String(data.responseSchemaName || '').trim();
	if (!name) {
		throw new Error('schema_name 不能为空');
	}
	let schema: any;
	try {
		schema = JSON.parse(data.responseSchemaBody || '{}');
	} catch {
		throw new Error('schema JSON 格式错误');
	}
	return JSON.stringify({
		type: 'json_schema',
		json_schema: {
			name,
			description: data.responseSchemaDescription || undefined,
			schema,
			strict: data.responseSchemaStrict !== false
		}
	});
}

function normalizeSingleId(value: any) {
	return Array.isArray(value) ? value[0] : value;
}
</script>

<style lang="scss" scoped>
.result {
	margin-top: 16px;
}

.response-format {
	width: 100%;

	.mt-2 {
		margin-top: 8px;
	}
}
</style>
