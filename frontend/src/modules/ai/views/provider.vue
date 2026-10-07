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
					<el-button text type="primary" @click="testProvider(scope.row)">{{
						$t('测试')
					}}</el-button>
				</template>
				<template #slot-sync="{ scope }">
					<el-button text type="primary" @click="syncModels(scope.row)">{{
						$t('同步模型')
					}}</el-button>
				</template>
			</cl-table>
		</cl-row>

		<cl-row>
			<cl-flex1 />
			<cl-pagination />
		</cl-row>

		<cl-upsert ref="Upsert">
			<template #slot-extraConfig="{ scope }">
				<div class="extra-config-editor">
					<div class="extra-config-editor__tools">
						<span>{{ $t('按适配器填充常用配置') }}</span>
						<el-button text type="primary" @click="fillExtraConfig(scope)">{{
							$t('填充模板')
						}}</el-button>
					</div>
					<cl-editor-codemirror v-model="scope.extraConfig" :height="200" />
				</div>
			</template>
		</cl-upsert>
	</cl-crud>

	<el-drawer v-model="catalog.visible" :title="$t('导入模型厂商预设')" size="720px">
		<el-table :data="catalog.items" border>
			<el-table-column prop="name" :label="$t('厂商')" min-width="140" />
			<el-table-column prop="adapter" :label="$t('适配器')" min-width="150" />
			<el-table-column :label="$t('模型')" min-width="180">
				<template #default="{ row }">
					<div class="catalog-types">
						<el-tag
							v-for="item in modelTypeStats(row)"
							:key="item.label"
							size="small"
							effect="plain"
						>
							{{ item.label }} {{ item.value }}
						</el-tag>
					</div>
				</template>
			</el-table-column>
			<el-table-column :label="$t('操作')" width="90" align="center">
				<template #default="{ row }">
					<el-button text type="primary" @click="importCatalog(row)">{{
						$t('导入')
					}}</el-button>
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
import { h, reactive, ref } from 'vue';
import { useCool } from '/@/cool';
import { useI18n } from 'vue-i18n';

const { service } = useCool();
const { t } = useI18n();

const adapterOptions = [
	{ label: 'OpenAI Compatible', value: 'openai-compatible' },
	{ label: 'Ollama', value: 'ollama' },
	{ label: 'Gemini', value: 'gemini' },
	{ label: 'Claude', value: 'claude' },
	{ label: 'DeepSeek', value: 'deepseek' },
	{ label: '火山方舟', value: 'volcengine-ark' },
	{ label: '阿里百炼', value: 'bailian' },
	{ label: '腾讯混元', value: 'hunyuan' },
	{ label: '百度千帆', value: 'qianfan' },
	{ label: '智谱 GLM', value: 'zhipu' },
	{ label: 'MiniMax', value: 'minimax' },
	{ label: '小米 MiMo', value: 'mimo' },
	{ label: 'ToAPIs', value: 'toapis' }
];
const extraConfigTemplates: Record<string, string> = {
	bailian: JSON.stringify(
		{
			timeout: 60,
			dashscope_base_url: 'https://dashscope.aliyuncs.com/api/v1',
			workspace_id: '',
			image_poll_interval_seconds: 2,
			image_poll_timeout_seconds: 180
		},
		null,
		2
	),
	'openai-compatible': JSON.stringify({ timeout: 60, skip_model_list_check: false }, null, 2),
	'volcengine-ark': JSON.stringify({ timeout: 60 }, null, 2),
	toapis: JSON.stringify(
		{
			timeout: 60,
			image_poll_interval_seconds: 3,
			image_poll_timeout_seconds: 600,
			skip_model_list_check: true
		},
		null,
		2
	)
};
const catalog = reactive({
	visible: false,
	items: [] as any[]
});

// 分组标题组件
function renderSection(title: string, desc?: string) {
	return () =>
		h('div', { class: 'form-section-header' }, [
			h('span', { class: 'form-section-header__bar' }),
			h('span', { class: 'form-section-header__title' }, title),
			desc ? h('span', { class: 'form-section-header__desc' }, desc) : null
		]);
}

// 跟踪用户是否手动修改过编码
const isCodeManuallyEdited = ref(false);

/**
 * 将名称/适配器转换为小写规范化 slug 编码
 */
function deriveCode(name?: string, adapter?: string): string {
	const text = String(name || '').trim();
	if (text) {
		const slug = text
			.toLowerCase()
			.replace(/[^a-z0-9\s-_]/g, '')
			.replace(/[\s_]+/g, '-')
			.replace(/-+/g, '-')
			.replace(/^-+|-+$/g, '');
		if (slug) {
			return slug;
		}
	}
	if (adapter && adapter !== 'openai-compatible') {
		return adapter.toLowerCase().replace(/_/g, '-');
	}
	return '';
}

const Upsert = useUpsert({
	dialog: { width: '800px' },
	props: { labelWidth: '120px' },
	items: [
		// --- 1. 基本信息 ---
		{
			prop: '_sec_base',
			span: 24,
			component: { vm: renderSection(t('基本信息'), t('配置厂商展示名称、唯一标识与适配器通道')) }
		},
		{
			label: t('名称'),
			prop: 'name',
			required: true,
			span: 12,
			component: {
				name: 'el-input',
				props: {
					placeholder: '例如: ToAPIs 官方 / OpenAI',
					onInput(val: string) {
						if (!isCodeManuallyEdited.value) {
							const currentAdapter = Upsert.value?.getForm('adapter');
							const derived = deriveCode(val, currentAdapter);
							if (derived) {
								Upsert.value?.setForm('code', derived);
							}
						}
					}
				}
			}
		},
		{
			label: t('编码'),
			prop: 'code',
			required: false,
			span: 12,
			component: {
				name: 'el-input',
				props: {
					placeholder: t('例如: toapis (留空根据名称自动生成)'),
					onInput() {
						isCodeManuallyEdited.value = true;
					}
				}
			}
		},
		{
			label: t('适配器'),
			prop: 'adapter',
			value: 'openai-compatible',
			required: true,
			span: 12,
			component: {
				name: 'cl-select',
				props: {
					options: adapterOptions,
					onChange(adapterVal: string) {
						if (!isCodeManuallyEdited.value) {
							const currentCode = Upsert.value?.getForm('code');
							if (!currentCode) {
								const currentName = Upsert.value?.getForm('name');
								const derived = deriveCode(currentName, adapterVal);
								if (derived) {
									Upsert.value?.setForm('code', derived);
								}
							}
						}
					}
				}
			}
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

		// --- 2. 接口与鉴权 ---
		{
			prop: '_sec_auth',
			span: 24,
			component: { vm: renderSection(t('接口与鉴权'), t('API 接入地址与访问授权密钥')) }
		},
		{
			label: 'Base URL',
			prop: 'baseUrl',
			span: 24,
			component: {
				name: 'el-input',
				props: { placeholder: '例如: https://api.toapis.cn 或 https://api.openai.com/v1' }
			}
		},
		{
			label: 'API Key',
			prop: 'apiKey',
			span: 24,
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
			label: t('管理 Access Key'),
			prop: 'adminAccessKey',
			span: 12,
			hidden: ({ scope }) => scope.adapter !== 'volcengine-ark',
			component: {
				name: 'el-input',
				props: {
					type: 'password',
					showPassword: true,
					placeholder: t('火山 OpenAPI AK，留空不修改')
				}
			}
		},
		{
			label: t('管理 Secret Key'),
			prop: 'adminSecretKey',
			span: 12,
			hidden: ({ scope }) => scope.adapter !== 'volcengine-ark',
			component: {
				name: 'el-input',
				props: {
					type: 'password',
					showPassword: true,
					placeholder: t('火山 OpenAPI SK，留空不修改')
				}
			}
		},

		// --- 3. 厂商扩展配置 ---
		{
			prop: '_sec_extra',
			span: 24,
			component: { vm: renderSection(t('厂商扩展配置'), t('高级参数 JSON，如超时时间、轮询频率等')) }
		},
		{
			label: t('扩展配置'),
			prop: 'extraConfig',
			span: 24,
			component: { name: 'slot-extraConfig' }
		},

		// --- 4. 状态控制 ---
		{
			prop: '_sec_control',
			span: 24,
			component: { vm: renderSection(t('状态控制'), t('控制厂商的整体启用与停用')) }
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
		const data = Upsert.value?.form;
		// 编辑已有厂商时保持 manual 标记，避免修改名称时意外改写已有编码；新增时重置
		isCodeManuallyEdited.value = Boolean(data?.id && data?.code);

		// 旧数据可能为 null，编辑器需有初始 JSON 串（仅在空值时兜底，避免覆盖编辑回填）
		if (data && data.extraConfig == null) {
			data.extraConfig = '{}';
		}
	},
	onInfo(data, { done }) {
		done({ ...data, apiKey: '', adminAccessKey: '', adminSecretKey: '' });
	},
	onSubmit(data, { next }) {
		const payload = { ...data };
		if (!payload.code || !String(payload.code).trim()) {
			payload.code = deriveCode(payload.name, payload.adapter);
		}
		Object.keys(payload).forEach(key => {
			if (key.startsWith('_')) {
				delete payload[key];
			}
		});
		next(payload);
	}
});

const Table = useTable({
	columns: [
		{ type: 'selection' },
		{ label: t('编码'), prop: 'code', minWidth: 150, hidden: true },
		{ label: t('名称'), prop: 'name', minWidth: 150 },
		{ label: t('适配器'), prop: 'adapter', minWidth: 150 },
		{ label: 'Base URL', prop: 'baseUrl', minWidth: 240, showOverflowTooltip: true, hidden: true },
		{ label: 'API Key', prop: 'apiKeyMask', minWidth: 130 },
		{ label: t('管理 AK'), prop: 'adminAccessKeyMask', minWidth: 130 },
		{ label: t('启用'), prop: 'status', width: 100, component: { name: 'cl-switch' } },
		{ label: t('创建时间'), prop: 'createTime', sortable: 'desc', minWidth: 170, component: { name: 'cl-date-text' } },
		{
			type: 'op',
			width: 340,
			buttons: ['edit', 'delete', 'slot-test', 'slot-sync']
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

async function syncModels(row: any) {
	try {
		const res = await service.ai.provider.syncModels({ id: row.id });
		ElMessage.success(
			`${t('同步完成')}，${t('新增')}: ${res?.created || 0}，${t('已更新')}: ${res?.updated || 0}`
		);
	} catch (err: any) {
		ElMessage.error(err.message || t('同步失败'));
	}
}

function fillExtraConfig(scope: any) {
	const adapter = scope.adapter || 'openai-compatible';
	scope.extraConfig = extraConfigTemplates[adapter] || JSON.stringify({ timeout: 60 }, null, 2);
}

function modelTypeStats(row: any) {
	const labels: Record<string, string> = {
		chat: t('对话'),
		embedding: t('向量'),
		image: t('图片'),
		rerank: t('重排'),
		audio: t('音频'),
		video: t('视频')
	};
	const counts: Record<string, number> = {};
	(row.models || []).forEach((item: any) => {
		const type = item.model_type || item.modelType || 'chat';
		counts[type] = (counts[type] || 0) + 1;
	});
	return Object.entries(counts).map(([key, value]) => ({ label: labels[key] || key, value }));
}
</script>

<style lang="scss" scoped>
.extra-config-editor {
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

.catalog-types {
	display: flex;
	flex-wrap: wrap;
	gap: 6px;
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
