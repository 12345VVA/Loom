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
					<el-button
						v-if="!scope.row.isDefault"
						text
						type="primary"
						@click="setDefault(scope.row)"
					>
						{{ $t('设为默认') }}
					</el-button>
					<el-tag v-else size="small" type="success">{{ $t('默认') }}</el-tag>
				</template>
				<template #slot-test="{ scope }">
					<el-button text type="primary" @click="openTest(scope.row)">
						{{ $t('测试') }}
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

	<el-drawer v-model="tester.visible" :title="$t('测试调用')" size="440px">
		<el-form label-position="top">
			<el-alert
				v-if="tester.modelType === 'image'"
				class="mb-12"
				type="info"
				:closable="false"
				show-icon
			>
				{{ $t('图片配置会调用统一生图接口，结果可直接预览。') }}
			</el-alert>
			<el-form-item :label="$t('提示词')">
				<el-input v-model="tester.prompt" type="textarea" :rows="6" />
			</el-form-item>
			<el-button type="primary" @click="runTest">{{ $t('调用') }}</el-button>
		</el-form>
		<div v-if="tester.imageItems.length" class="test-images">
			<div v-for="(item, index) in tester.imageItems" :key="index" class="test-image">
				<el-image
					:src="item.src"
					fit="contain"
					:preview-src-list="tester.imageItems.map(i => i.src)"
					:initial-index="index"
					preview-teleported
				/>
				<el-button text type="primary" @click="copyText(item.value)">{{
					$t('复制')
				}}</el-button>
			</div>
		</div>
		<el-input
			v-if="tester.result"
			v-model="tester.result"
			type="textarea"
			:rows="12"
			class="result"
		/>
	</el-drawer>
</template>

<script lang="ts" setup>
defineOptions({
	name: 'ai-profile'
});

import { useCrud, useTable, useUpsert } from '@cool-vue/crud';
import { ElMessage } from 'element-plus';
import { h, markRaw, onMounted, reactive, ref } from 'vue';
import { ElIcon, ElTooltip } from 'element-plus';
import { InfoFilled } from '@element-plus/icons-vue';
import { useCool } from '/@/cool';
import { useI18n } from 'vue-i18n';
import { extractImageItems } from '../utils/image-utils';
import ResponseFormatEditor from '../components/response-format-editor.vue';

const { service } = useCool();
const { t } = useI18n();

const tester = reactive({
	visible: false,
	id: 0,
	modelType: '',
	prompt: '你好，请用一句话介绍你自己。',
	result: '',
	imageItems: [] as { src: string; value: string; url?: string }[]
});

const modelsList = ref<any[]>([]);

onMounted(async () => {
	try {
		const res = await service.ai.model.list({});
		modelsList.value = res || [];
	} catch (e) {
		console.warn('加载模型列表失败:', e);
	}
});

function getModelType(scope: any): string {
	if (!scope) return '';
	if (scope.modelType) return scope.modelType;
	if (scope.modelId) {
		const m = modelsList.value.find((item: any) => item.id == scope.modelId);
		if (m) return m.modelType || '';
	}
	return '';
}

function isChatModel(scope: any): boolean {
	const type = getModelType(scope);
	return type === 'chat' || type === 'llm';
}

// 表单标签旁的 tooltip 图标（ui-guidelines：解释性小字图标化）
function renderLabelWithTip(label: string, tip: string) {
	return () =>
		h('span', { class: 'label-with-tip' }, [
			label,
			h(
				ElTooltip,
				{ content: tip, placement: 'top', effect: 'dark' },
				{ default: () => h(ElIcon, { class: 'label-tip-icon' }, { default: () => h(InfoFilled) }) }
			)
		]);
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

// 跟踪用户是否手动修改过名称与编码
const isCodeManuallyEdited = ref(false);
const isNameManuallyEdited = ref(false);

function deriveProfileSlug(text: string): string {
	if (!text) return '';
	return text
		.toLowerCase()
		.replace(/[^a-z0-9\s-_]/g, '')
		.replace(/[\s_]+/g, '-')
		.replace(/-+/g, '-')
		.replace(/^-+|-+$/g, '');
}

function handleModelChange(val: any) {
	const mid = normalizeSingleId(val);
	if (!mid) return;
	const m = modelsList.value.find((item: any) => item.id == mid);
	if (!m) return;

	const currentScenario = Upsert.value?.getForm('scenario') || 'default';
	const modelName = m.name || m.code || '';
	const modelCode = m.code || '';

	// 1. 若名称未手动修改，建议名称："{模型名} ({场景})"
	if (!isNameManuallyEdited.value && modelName) {
		Upsert.value?.setForm('name', `${modelName} (${currentScenario})`);
	}

	// 2. 若编码未手动修改，建议编码："{modelCode/slug}-{scenario}"
	if (!isCodeManuallyEdited.value) {
		const base = (modelCode || deriveProfileSlug(modelName)).toLowerCase().replace(/[^a-z0-9-_]/g, '-');
		const scen = String(currentScenario).toLowerCase().replace(/[^a-z0-9-_]/g, '-');
		const code = `${base}-${scen}`.replace(/-+/g, '-').replace(/^-+|-+$/g, '');
		if (code) {
			Upsert.value?.setForm('code', code);
		}
	}
}

function handleScenarioInput(scenVal: string) {
	const currentMid = normalizeSingleId(Upsert.value?.getForm('modelId'));
	const m = currentMid ? modelsList.value.find((item: any) => item.id == currentMid) : null;
	const scen = String(scenVal || 'default').trim();

	if (!isNameManuallyEdited.value && m) {
		const modelName = m.name || m.code || '';
		Upsert.value?.setForm('name', `${modelName} (${scen})`);
	}

	if (!isCodeManuallyEdited.value) {
		const base = (m?.code || deriveProfileSlug(Upsert.value?.getForm('name') || '')).toLowerCase().replace(/[^a-z0-9-_]/g, '-');
		if (base) {
			const scenSlug = scen.toLowerCase().replace(/[^a-z0-9-_]/g, '-');
			const code = `${base}-${scenSlug}`.replace(/-+/g, '-').replace(/^-+|-+$/g, '');
			Upsert.value?.setForm('code', code);
		}
	}
}

function handleNameInput(nameVal: string) {
	isNameManuallyEdited.value = true;
	if (!isCodeManuallyEdited.value) {
		const slug = deriveProfileSlug(nameVal);
		if (slug) {
			Upsert.value?.setForm('code', slug);
		}
	}
}

const Upsert = useUpsert({
	dialog: { width: '840px' },
	props: { labelWidth: '120px' },
	items: [
		// --- 1. 基本信息 ---
		{
			prop: '_sec_base',
			span: 24,
			component: { vm: renderSection(t('基本信息'), t('配置关联模型、业务场景、调用编码与展示名称')) }
		},
		{
			label: t('模型'),
			prop: 'modelId',
			required: true,
			span: 12,
			component: {
				name: 'cl-select-table',
				props: {
					service: service.ai.model,
					multiple: false,
					dict: { text: 'name' },
					columns: [
						{ label: t('厂商'), prop: 'providerName', minWidth: 140 },
						{ label: t('编码'), prop: 'code', minWidth: 160 },
						{ label: t('类型'), prop: 'modelType', minWidth: 110 }
					],
					onChange(val: any) {
						handleModelChange(val);
					}
				}
			}
		},
		{
			label: t('场景'),
			prop: 'scenario',
			value: 'default',
			required: true,
			span: 12,
			component: {
				name: 'el-input',
				props: {
					placeholder: 'default / workflow / image',
					onInput(val: string) {
						handleScenarioInput(val);
					}
				}
			}
		},
		{
			label: t('名称'),
			prop: 'name',
			required: true,
			span: 12,
			component: {
				name: 'el-input',
				props: {
					placeholder: '例如: GPT-Image-2.5 Flare VIP',
					onInput(val: string) {
						handleNameInput(val);
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
					placeholder: t('例如: deepseek-v3-default (留空自动生成)'),
					onInput() {
						isCodeManuallyEdited.value = true;
					}
				}
			}
		},

		// --- 2. 模型推理参数 ---
		{
			prop: '_sec_params',
			span: 24,
			component: { vm: renderSection(t('模型推理参数'), t('控制输出随机性、长度限制、响应格式与函数工具')) }
		},
		{
			label: t('采样温度'),
			renderLabel: renderLabelWithTip(t('采样温度'), t('控制输出随机性，范围 0-2，精确任务建议调低')),
			prop: 'temperature',
			span: 8,
			component: {
				name: 'el-input-number',
				props: {
					min: 0,
					max: 2,
					step: 0.1,
					placeholder: '默认 0.7',
					'controls-position': 'right',
					style: { width: '100%' }
				}
			}
		},
		{
			label: t('核采样 (Top-P)'),
			renderLabel: renderLabelWithTip(
				t('核采样 (Top-P)'),
				t('仅保留累计概率前 P 的词元，值越小输出越确定')
			),
			prop: 'topP',
			span: 8,
			component: {
				name: 'el-input-number',
				props: {
					min: 0,
					max: 1,
					step: 0.05,
					placeholder: '默认 1.0',
					'controls-position': 'right',
					style: { width: '100%' }
				}
			}
		},
		{
			label: t('单次最大 Token'),
			renderLabel: renderLabelWithTip(t('单次最大 Token'), t('限制单次回复生成的最大 Token 数')),
			prop: 'maxTokens',
			span: 8,
			component: {
				name: 'el-input-number',
				props: {
					min: 1,
					placeholder: '默认 (不限)',
					'controls-position': 'right',
					style: { width: '100%' }
				}
			}
		},
		{
			label: t('响应格式'),
			prop: 'responseFormat',
			span: 24,
			hidden: ({ scope }) => !isChatModel(scope),
			component: {
				name: 'response-format-editor',
				vm: markRaw(ResponseFormatEditor)
			}
		},
		{
			label: t('工具集 (tools)'),
			renderLabel: renderLabelWithTip(
				t('工具集 (tools)'),
				t('JSON 数组，声明模型可调用的工具（Function Calling）')
			),
			prop: 'toolsConfig',
			span: 24,
			hidden: ({ scope }) => !isChatModel(scope),
			component: { name: 'cl-editor', props: { name: 'cl-editor-codemirror', height: 180 } }
		},
		{
			prop: '_hint_non_chat',
			span: 24,
			hidden: ({ scope }) => isChatModel(scope),
			component: {
				vm: () =>
					h('div', { class: 'non-chat-tip' }, [
						h(ElIcon, { class: 'mr-1' }, { default: () => h(InfoFilled) }),
						h(
							'span',
							t('当前所选模型为非对话模型（如生图/视频/向量等），不需要且不支持设置响应格式与函数工具集。')
						)
					])
			}
		},

		// --- 3. 运行调度与容灾 ---
		{
			prop: '_sec_schedule',
			span: 24,
			component: { vm: renderSection(t('运行调度与容灾'), t('超时控制、异常重试与故障转移降级')) }
		},
		{
			label: t('超时时间 (秒)'),
			renderLabel: renderLabelWithTip(t('超时时间 (秒)'), t('单次调用允许的最长等待时间')),
			prop: 'timeout',
			span: 12,
			component: {
				name: 'el-input-number',
				props: {
					min: 1,
					placeholder: '留空使用默认',
					'controls-position': 'right',
					style: { width: '100%' }
				}
			}
		},
		{
			label: t('重试次数'),
			renderLabel: renderLabelWithTip(t('重试次数'), t('调用失败后自动重试的次数上限')),
			prop: 'retryCount',
			value: 0,
			span: 12,
			component: {
				name: 'el-input-number',
				props: { min: 0, max: 5, 'controls-position': 'right', style: { width: '100%' } }
			}
		},
		{
			label: t('重试间隔 (秒)'),
			renderLabel: renderLabelWithTip(t('重试间隔 (秒)'), t('两次重试之间的等待时间')),
			prop: 'retryDelaySeconds',
			value: 0,
			span: 12,
			component: {
				name: 'el-input-number',
				props: { min: 0, max: 60, 'controls-position': 'right', style: { width: '100%' } }
			}
		},
		{
			label: t('兜底配置ID'),
			renderLabel: renderLabelWithTip(t('兜底配置ID'), t('主模型调用失败时用于降级容灾的备用 Profile ID')),
			prop: 'fallbackProfileId',
			span: 12,
			component: {
				name: 'el-input-number',
				props: {
					min: 1,
					placeholder: '选填备用 Profile ID',
					'controls-position': 'right',
					style: { width: '100%' }
				}
			}
		},

		// --- 4. 状态与控制 ---
		{
			prop: '_sec_control',
			span: 24,
			component: { vm: renderSection(t('状态与控制'), t('排序权重、默认命中与启用状态')) }
		},
		{
			label: t('排序'),
			prop: 'orderNum',
			value: 0,
			span: 8,
			component: {
				name: 'el-input-number',
				props: { 'controls-position': 'right', style: { width: '100%' } }
			}
		},
		{
			label: t('默认'),
			prop: 'isDefault',
			value: false,
			span: 8,
			component: { name: 'el-switch' }
		},
		{
			label: t('启用'),
			prop: 'status',
			value: true,
			span: 8,
			component: { name: 'el-switch' }
		}
	],
	onOpen() {
		const data = Upsert.value?.form;
		// 编辑已有配置时保持 manual 标记，避免修改模型/场景时意外改写已有编码与名称；新增时重置
		isCodeManuallyEdited.value = Boolean(data?.id && data?.code);
		isNameManuallyEdited.value = Boolean(data?.id && data?.name);

		if (data && data.modelId && !data.modelType) {
			const m = modelsList.value.find((item: any) => item.id == data.modelId);
			if (m) data.modelType = m.modelType;
		}
	},
	onSubmit(data, { next }) {
		const payload = { ...data };
		if (!payload.code || !String(payload.code).trim()) {
			const currentMid = normalizeSingleId(payload.modelId);
			const m = currentMid ? modelsList.value.find((item: any) => item.id == currentMid) : null;
			const base = (m?.code || deriveProfileSlug(payload.name || '') || 'profile').toLowerCase().replace(/[^a-z0-9-_]/g, '-');
			const scen = String(payload.scenario || 'default').toLowerCase().replace(/[^a-z0-9-_]/g, '-');
			payload.code = `${base}-${scen}`.replace(/-+/g, '-').replace(/^-+|-+$/g, '');
		}
		Object.keys(payload).forEach(key => {
			if (key.startsWith('_')) {
				delete payload[key];
			}
		});
		// 非对话模型时，清理响应格式与工具集（置 null 触发后端显式清空更新）
		const type = getModelType(payload);
		if (type && type !== 'chat' && type !== 'llm') {
			payload.responseFormat = null;
			payload.toolsConfig = null;
		}
		next({
			...payload,
			modelId: normalizeSingleId(payload.modelId),
			// text 模式下编辑器产出空串，按 null 或实际字符串提交
			responseFormat: payload.responseFormat ?? null
		});
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
		{ label: t('创建时间'), prop: 'createTime', sortable: 'desc', minWidth: 170, component: { name: 'cl-date-text' } },
		{
			type: 'op',
			width: 280,
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
	tester.modelType = row.modelType || '';
	tester.prompt =
		row.modelType === 'image'
			? '一张干净的 AI 内容平台海报，科技感，高质量细节'
			: '你好，请用一句话介绍你自己。';
	tester.result = '';
	tester.imageItems = [];
	tester.visible = true;
}

async function runTest() {
	try {
		const res = await service.ai.profile.test({ id: tester.id, prompt: tester.prompt });
		tester.result = JSON.stringify(res, null, 2);
		tester.imageItems = tester.modelType === 'image' ? extractImageItems(res) : [];
	} catch (err: any) {
		ElMessage.error(err.message || t('调用失败'));
	}
}

function normalizeSingleId(value: any) {
	return Array.isArray(value) ? value[0] : value;
}

async function copyText(value: string) {
	await navigator.clipboard.writeText(value);
	ElMessage.success(t('已复制'));
}
</script>

<style lang="scss" scoped>
.result {
	margin-top: 16px;
}

.mb-12 {
	margin-bottom: 12px;
}

.test-images {
	display: grid;
	grid-template-columns: repeat(auto-fill, minmax(160px, 1fr));
	gap: 10px;
	margin-top: 14px;
}

.test-image {
	border: 1px solid var(--el-border-color-lighter);
	border-radius: 6px;
	overflow: hidden;

	.el-image {
		display: block;
		width: 100%;
		height: 160px;
		background: var(--el-fill-color-light);
	}
}

.label-with-tip {
	display: inline-flex;
	align-items: center;
	gap: 4px;

	.label-tip-icon {
		color: var(--el-text-color-placeholder);
		cursor: help;
		transition: color 0.3s;

		&:hover {
			color: var(--el-color-primary);
		}
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

:deep(.non-chat-tip) {
	display: flex;
	align-items: center;
	padding: 8px 12px;
	margin-top: 2px;
	font-size: 12px;
	line-height: 1.4;
	color: var(--el-color-info);
	background-color: var(--el-color-info-light-9);
	border: 1px dashed var(--el-color-info-light-5);
	border-radius: 4px;
}
</style>
