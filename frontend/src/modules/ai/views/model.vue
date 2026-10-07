<template>
	<cl-crud ref="Crud">
		<cl-row>
			<cl-refresh-btn />
			<cl-add-btn />
			<cl-multi-delete-btn />
			<cl-filter :label="$t('模型类型')">
				<cl-select :options="modelTypeOptions" prop="modelType" :width="130" />
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
						<el-button text type="primary" @click="fillPricingConfig(scope)">{{
							$t('填充示例')
						}}</el-button>
					</div>
					<cl-editor-codemirror v-model="scope.pricingConfig" :height="150" />
				</div>
			</template>
			<template #slot-defaultConfig="{ scope }">
				<div class="default-config-editor">
					<div class="default-config-editor__tools">
						<span>{{ defaultConfigHint(scope) }}</span>
						<el-button text type="primary" @click="fillDefaultConfig(scope)">{{
							$t('填充示例')
						}}</el-button>
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

import { computed, h, onMounted } from 'vue';
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

// 分组标题组件
function renderSection(title: string, desc?: string) {
	return () =>
		h('div', { class: 'form-section-header' }, [
			h('span', { class: 'form-section-header__bar' }),
			h('span', { class: 'form-section-header__title' }, title),
			desc ? h('span', { class: 'form-section-header__desc' }, desc) : null
		]);
}

const Upsert = useUpsert({
	dialog: { width: '840px' },
	props: { labelWidth: '110px' },
	items: [
		// --- 1. 基本信息 ---
		{
			prop: '_sec_base',
			span: 24,
			component: { vm: renderSection(t('基本信息'), t('配置模型所属厂商、类型、编码与展示名称')) }
		},
		{
			label: t('厂商'),
			prop: 'providerId',
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
			value: 'chat',
			required: true,
			span: 12,
			component: { name: 'cl-select', props: { options: modelTypeOptions } }
		},
		{
			label: t('编码'),
			prop: 'code',
			required: true,
			span: 12,
			component: { name: 'el-input', props: { placeholder: '例如: gpt-image-2.5-flare' } }
		},
		{
			label: t('名称'),
			prop: 'name',
			required: true,
			span: 12,
			component: { name: 'el-input', props: { placeholder: '例如: GPT-Image-2.5 Flare' } }
		},
		{
			label: t('能力标签'),
			prop: 'capabilities',
			span: 24,
			component: { name: 'slot-capabilities' }
		},

		// --- 2. 上下文与Token规格（仅对话/LLM模型显示） ---
		{
			prop: '_sec_context',
			span: 24,
			hidden: ({ scope }) => !isChatModel(scope),
			component: { vm: renderSection(t('容量规格'), t('限制上下文窗口大小与最大生成长度')) }
		},
		{
			label: t('上下文长度'),
			prop: 'contextWindow',
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
			span: 12,
			hidden: ({ scope }) => !isChatModel(scope),
			component: {
				name: 'el-input-number',
				props: { min: 1, placeholder: '例如: 4096', 'controls-position': 'right', style: { width: '100%' } }
			}
		},

		// --- 3. 价格与默认配置 ---
		{
			prop: '_sec_config',
			span: 24,
			component: { vm: renderSection(t('配置与参数'), t('模型调用计费规则与默认启动参数')) }
		},
		{
			label: t('价格配置'),
			prop: 'pricingConfig',
			span: 24,
			component: { name: 'slot-pricingConfig' }
		},
		{
			label: t('默认参数'),
			prop: 'defaultConfig',
			span: 24,
			component: { name: 'slot-defaultConfig' }
		},

		// --- 4. 状态与控制 ---
		{
			prop: '_sec_control',
			span: 24,
			component: { vm: renderSection(t('状态与控制'), t('排序优先级与启用状态')) }
		},
		{
			label: t('排序'),
			prop: 'orderNum',
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
		Object.keys(payload).forEach(key => {
			if (key.startsWith('_')) {
				delete payload[key];
			}
		});
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
		{ type: 'selection' },
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
		{ type: 'op', buttons: ['edit', 'delete'] }
	]
});

const Crud = useCrud(
	{
		service: service.ai.model
	},
	app => {
		app.refresh();
	}
);

function splitCapabilities(value?: string | null) {
	return String(value || '')
		.split(',')
		.map(item => item.trim())
		.filter(Boolean);
}

function formatCapabilities(value?: string | null) {
	const list = splitCapabilities(value);
	if (!list.length) return '-';
	const dictItems = dict.get('ai_model_capability').value || [];
	const map = new Map(dictItems.map((item: { value: unknown; label: string }) => [String(item.value), item.label]));
	return list
		.map(item => {
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

function defaultConfigPlaceholder(scope: Record<string, unknown>) {
	return JSON.stringify(defaultConfigTemplate(scope), null, 2);
}

function fillDefaultConfig(scope: Record<string, unknown>) {
	scope.defaultConfig = defaultConfigPlaceholder(scope);
}

function fillPricingConfig(scope: Record<string, unknown>) {
	scope.pricingConfig = JSON.stringify({ input: 0, output: 0 }, null, 2);
}

function defaultConfigTemplate(scope: Record<string, unknown>) {
	if (scope.modelType === 'image') {
		return {
			size: '1024x1024',
			_size_format: 'pixel',
			_allow_custom_size: true,
			_sizes: [
				{ label: '1024x1024 (1:1)', value: '1024x1024' },
				{ label: '768x1024 (3:4)', value: '768x1024' },
				{ label: '1024x768 (4:3)', value: '1024x768' },
				{ label: '720x1280 (9:16)', value: '720x1280' },
				{ label: '1280x720 (16:9)', value: '1280x720' }
			],
			_limits: { max_n: 4 }
		};
	}
	if (scope.modelType === 'embedding') {
		return {};
	}
	return {
		temperature: 0.7,
		top_p: 0.9,
		max_tokens: 1024
	};
}
</script>

<style lang="scss" scoped>
.capability-option-item {
	display: flex;
	align-items: center;
	justify-content: space-between;
	width: 100%;

	.capability-option-code {
		font-size: 12px;
		color: var(--el-text-color-secondary);
		margin-left: 16px;
	}
}

.capability-tip-icon {
	font-size: 16px;
	color: var(--el-text-color-placeholder);
	cursor: help;
	transition: color 0.3s;

	&:hover {
		color: var(--el-color-primary);
	}
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

:deep(.form-section-header) {
	display: flex;
	align-items: center;
	padding: 8px 0 6px;
	margin: 6px 0 4px;
	border-bottom: 1px solid var(--el-border-color-lighter);

	.form-section-header__bar {
		width: 3px;
		height: 14px;
		background: var(--el-color-primary);
		border-radius: 2px;
		margin-right: 8px;
		flex-shrink: 0;
	}

	.form-section-header__title {
		font-size: 13px;
		font-weight: 600;
		color: var(--el-text-color-primary);
		letter-spacing: 0.3px;
	}

	.form-section-header__desc {
		font-size: 12px;
		color: var(--el-text-color-placeholder);
		margin-left: 8px;
	}
}
</style>
