<template>
	<cl-crud ref="Crud">
		<cl-row>
			<cl-refresh-btn />
			<cl-add-btn />
			<cl-multi-delete-btn />
			<cl-filter :label="$t('模型类型')">
				<cl-select :options="modelTypeOptions" prop="modelType" :width="130" clearable />
			</cl-filter>
			<cl-flex1 />
			<el-tooltip
				:content="$t('能力字段是模型元信息，未实现接口仍会返回 501。')"
				placement="top"
				effect="dark"
			>
				<el-icon class="capability-tip-icon"><info-filled /></el-icon>
			</el-tooltip>
			<cl-search-key :placeholder="$t('搜索编码、名称')" />
		</cl-row>

		<cl-row>
			<cl-table ref="Table" />
		</cl-row>

		<cl-row>
			<cl-flex1 />
			<cl-pagination />
		</cl-row>

		<cl-upsert ref="Upsert">
			<template #slot-capabilities="{ scope }">
				<el-select
					v-model="scope.capabilities"
					multiple
					filterable
					allow-create
					default-first-option
					clearable
					collapse-tags
					collapse-tags-tooltip
					:placeholder="$t('请选择或输入能力标签')"
					style="width: 100%"
				>
					<el-option
						v-for="item in capabilityOptions"
						:key="item.value"
						:label="item.label"
						:value="item.value"
					>
						<div class="capability-option-item">
							<span>{{ item.label }}</span>
							<span class="capability-option-code">{{ item.value }}</span>
						</div>
					</el-option>
				</el-select>
			</template>
			<template #slot-pricingConfig="{ scope }">
				<div class="default-config-editor">
					<div class="default-config-editor__tools">
						<span>{{ $t('模型调用价格配置') }}</span>
						<el-button text type="primary" @click="fillPricingConfig(scope)">
							{{ $t('填充示例') }}
						</el-button>
					</div>
					<cl-editor-codemirror v-model="scope.pricingConfig" :height="150" />
				</div>
			</template>
			<template #slot-defaultConfig="{ scope }">
				<div class="default-config-editor">
					<div class="default-config-editor__tools">
						<span>{{ defaultConfigHint(scope) }}</span>
						<el-button text type="primary" @click="fillDefaultConfig(scope)">
							{{ $t('填充示例') }}
						</el-button>
					</div>
					<cl-editor-codemirror v-model="scope.defaultConfig" :height="200" />
				</div>
			</template>
		</cl-upsert>
	</cl-crud>
</template>

<script lang="ts" setup>
defineOptions({
	name: 'ai-model'
});

import { computed, onMounted } from 'vue';
import { useCrud, useTable, useUpsert } from '@cool-vue/crud';
import { useCool } from '/@/cool';
import { useDict } from '/$/dict';
import { useI18n } from 'vue-i18n';
import { InfoFilled } from '@element-plus/icons-vue';

const { service } = useCool();
const { dict } = useDict();
const { t } = useI18n();

const capabilityOptions = computed(() => {
	return dict.get('ai_model_capability', 'asc').value || [];
});

onMounted(() => {
	if (!dict.get('ai_model_capability').value?.length) {
		dict.refresh(['ai_model_capability']);
	}
});

const modelTypeOptions = [
	{ label: t('对话'), value: 'chat', type: 'primary' },
	{ label: t('向量'), value: 'embedding', type: 'success' },
	{ label: t('图片'), value: 'image', type: 'warning' },
	{ label: t('音频'), value: 'audio', type: 'danger' },
	{ label: t('视频'), value: 'video', type: 'info' },
	{ label: t('重排'), value: 'rerank', type: 'success' }
];

function isChatModel(scope: Record<string, unknown>): boolean {
	const type = scope?.modelType;
	return type === 'chat' || type === 'llm';
}

// ---- Upsert 配置（标准 tabs 分组，消除虚假 prop，cool-crud-conventions.mdc） ----
const Upsert = useUpsert({
	dialog: { width: '840px' },
	props: { labelWidth: '110px' },
	items: [
		{
			type: 'tabs',
			props: {
				type: 'card',
				labels: [
					{ label: t('基本信息'), value: 'base' },
					{ label: t('规格与参数'), value: 'config' },
					{ label: t('状态控制'), value: 'control' }
				]
			}
		},
		// --- 1. 基本信息 ---
		{
			label: t('厂商'),
			prop: 'providerId',
			group: 'base',
			required: true,
			span: 12,
			component: {
				name: 'cl-select-table',
				props: {
					service: service.ai.provider,
					multiple: false,
					dict: { text: 'name' },
					columns: [
						{ label: t('编码'), prop: 'code', minWidth: 140 },
						{ label: t('名称'), prop: 'name', minWidth: 140 },
						{ label: t('适配器'), prop: 'adapter', minWidth: 140 }
					]
				}
			}
		},
		{
			label: t('模型类型'),
			prop: 'modelType',
			group: 'base',
			value: 'chat',
			required: true,
			span: 12,
			component: { name: 'cl-select', props: { options: modelTypeOptions } }
		},
		{
			label: t('编码'),
			prop: 'code',
			group: 'base',
			required: true,
			span: 12,
			component: { name: 'el-input', props: { placeholder: '例如: gpt-image-2.5-flare' } }
		},
		{
			label: t('名称'),
			prop: 'name',
			group: 'base',
			required: true,
			span: 12,
			component: { name: 'el-input', props: { placeholder: '例如: GPT-Image-2.5 Flare' } }
		},
		{
			label: t('能力标签'),
			prop: 'capabilities',
			group: 'base',
			span: 24,
			component: { name: 'slot-capabilities' }
		},

		// --- 2. 规格与参数 ---
		{
			label: t('上下文长度'),
			prop: 'contextWindow',
			group: 'config',
			span: 12,
			hidden: ({ scope }) => !isChatModel(scope),
			component: {
				name: 'el-input-number',
				props: { min: 1, placeholder: '例如: 128000', 'controls-position': 'right', style: { width: '100%' } }
			}
		},
		{
			label: t('最大输出'),
			prop: 'maxOutputTokens',
			group: 'config',
			span: 12,
			hidden: ({ scope }) => !isChatModel(scope),
			component: {
				name: 'el-input-number',
				props: { min: 1, placeholder: '例如: 4096', 'controls-position': 'right', style: { width: '100%' } }
			}
		},
		{
			label: t('价格配置'),
			prop: 'pricingConfig',
			group: 'config',
			span: 24,
			component: { name: 'slot-pricingConfig' }
		},
		{
			label: t('默认参数'),
			prop: 'defaultConfig',
			group: 'config',
			span: 24,
			component: { name: 'slot-defaultConfig' }
		},

		// --- 3. 状态与控制 ---
		{
			label: t('排序'),
			prop: 'orderNum',
			group: 'control',
			value: 0,
			span: 12,
			component: {
				name: 'el-input-number',
				props: { 'controls-position': 'right', style: { width: '100%' } }
			}
		},
		{
			label: t('启用'),
			prop: 'status',
			group: 'control',
			value: true,
			span: 12,
			component: { name: 'el-switch' }
		}
	],
	onOpen() {
		// 旧数据可能为 null，编辑器需有初始 JSON 串（仅在空值时兜底，避免覆盖编辑回填）
		const data = Upsert.value?.form;
		if (data) {
			if (data.pricingConfig == null) {
				data.pricingConfig = '{}';
			}
			if (data.defaultConfig == null) {
				data.defaultConfig = '{}';
			}
			if (typeof data.capabilities === 'string') {
				data.capabilities = splitCapabilities(data.capabilities);
			} else if (!Array.isArray(data.capabilities)) {
				data.capabilities = [];
			}
		}
	},
	async onInfo(data, { next, done }) {
		const res = await next(data);
		if (res) {
			if (res.pricingConfig == null) {
				res.pricingConfig = '{}';
			}
			if (res.defaultConfig == null) {
				res.defaultConfig = '{}';
			}
			if (typeof res.capabilities === 'string') {
				res.capabilities = splitCapabilities(res.capabilities);
			} else if (!Array.isArray(res.capabilities)) {
				res.capabilities = [];
			}
		}
		done(res);
	},
	onSubmit(data, { next }) {
		const payload = { ...data };
		if (Array.isArray(payload.capabilities)) {
			payload.capabilities = payload.capabilities.filter(Boolean).join(',');
		}
		// 非对话模型清空上下文与最大输出（传 null 显式更新，防止被 exclude_unset 跳过）
		if (!isChatModel(payload)) {
			payload.contextWindow = null;
			payload.maxOutputTokens = null;
		}
		next(payload);
	}
});

const Table = useTable({
	columns: [
		{ type: 'selection', width: 60 },
		{ label: t('名称'), prop: 'name', minWidth: 160 },
		{ label: t('厂商'), prop: 'providerName', minWidth: 150 },
		{ label: t('编码'), prop: 'code', minWidth: 180, hidden: true },
		{
			label: t('类型'),
			prop: 'modelType',
			minWidth: 120,
			dict: modelTypeOptions,
			dictColor: true
		},
		{
			label: t('能力'),
			prop: 'capabilities',
			minWidth: 220,
			showOverflowTooltip: true,
			formatter: ({ capabilities }: { capabilities?: string | null }) => formatCapabilities(capabilities),
			hidden: true
		},
		{ label: t('上下文'), prop: 'contextWindow', minWidth: 110 },
		{ label: t('最大输出'), prop: 'maxOutputTokens', minWidth: 110 },
		{ label: t('启用'), prop: 'status', width: 100, component: { name: 'cl-switch' } },
		{ label: t('创建时间'), prop: 'createTime', sortable: 'desc', minWidth: 170, component: { name: 'cl-date-text' } },
		{ type: 'op', width: 160, fixed: 'right', buttons: ['edit', 'delete'] }
	],
	contextMenu: ['refresh', 'check', 'edit', 'delete']
});

const Crud = useCrud(
	{
		service: service.ai.model
	},
	(app) => {
		app.refresh();
	}
);

function splitCapabilities(value?: string | null) {
	return String(value || '')
		.split(',')
		.map((item) => item.trim())
		.filter(Boolean);
}

function formatCapabilities(value?: string | null) {
	const list = splitCapabilities(value);
	if (!list.length) return '-';
	const dictItems = dict.get('ai_model_capability').value || [];
	const map = new Map(dictItems.map((item: { value: unknown; label: string }) => [String(item.value), item.label]));
	return list
		.map((item) => {
			const label = map.get(item);
			return label ? `${label} (${item})` : item;
		})
		.join(' / ');
}

function defaultConfigHint(scope: Record<string, unknown>) {
	if (scope.modelType === 'image') {
		return t('图片模型：可配置 size, _size_format(pixel/ratio), _allow_custom_size, _sizes, _limits 等');
	}
	if (scope.modelType === 'chat') {
		return t('对话模型默认参数');
	}
	return t('模型默认参数 JSON');
}

function fillPricingConfig(scope: Record<string, unknown>) {
	scope.pricingConfig = JSON.stringify(
		{
			input_cost_per_million_tokens: 0,
			output_cost_per_million_tokens: 0,
			currency: 'USD'
		},
		null,
		2
	);
}

function fillDefaultConfig(scope: Record<string, unknown>) {
	if (scope.modelType === 'image') {
		scope.defaultConfig = JSON.stringify(
			{
				size: '1024x1024',
				_size_format: 'pixel',
				_sizes: ['1024x1024', '768x1024', '1024x768', '512x512'],
				_allow_custom_size: true,
				_limits: {
					min_width: 256,
					max_width: 2048,
					min_height: 256,
					max_height: 2048
				}
			},
			null,
			2
		);
		return;
	}
	scope.defaultConfig = JSON.stringify(
		{
			temperature: 0.7,
			top_p: 1.0
		},
		null,
		2
	);
}
</script>

<style lang="scss" scoped>
.capability-tip-icon {
	color: var(--el-text-color-secondary);
	margin-right: 8px;
	cursor: pointer;
}

.capability-option-item {
	display: flex;
	align-items: center;
	justify-content: space-between;
	gap: 12px;
}

.capability-option-code {
	color: var(--el-text-color-secondary);
	font-size: 12px;
}

.default-config-editor {
	width: 100%;

	&__tools {
		display: flex;
		align-items: center;
		justify-content: space-between;
		margin-bottom: 8px;
		color: var(--el-text-color-secondary);
		font-size: 13px;
	}
}
</style>
