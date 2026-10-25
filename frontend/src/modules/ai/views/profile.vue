<template>
	<cl-crud ref="Crud">
		<cl-row>
			<cl-refresh-btn />
			<cl-add-btn />
			<cl-multi-delete-btn />
			<cl-filter :label="t('类型')">
				<cl-select :options="modelTypeOptions" prop="modelType" :width="120" clearable />
			</cl-filter>
			<cl-flex1 />
			<cl-search-key :placeholder="$t('搜索编码、名称、场景')" />
		</cl-row>

		<cl-row>
			<cl-table ref="Table">
				<template #slot-default="{ scope }">
					<el-button
						v-if="!scope.row.isDefault"
						v-permission="service.ai.profile.permission?.setDefault"
						text
						type="primary"
						@click="setDefault(scope.row)"
					>
						{{ $t('设为默认') }}
					</el-button>
					<el-tag v-else size="small" type="success">{{ $t('默认') }}</el-tag>
				</template>
				<template #slot-test="{ scope }">
					<el-button
						v-permission="service.ai.profile.permission?.test"
						text
						type="primary"
						@click="openTest(scope.row)"
					>
						{{ $t('测试') }}
					</el-button>
				</template>
			</cl-table>
		</cl-row>

		<cl-row>
			<cl-flex1 />
			<cl-pagination />
		</cl-row>

		<cl-upsert ref="Upsert">
			<template #slot-customConfig="{ scope }">
				<div class="custom-config-editor">
					<div class="custom-config-editor__tools">
						<span class="custom-config-editor__hint">
							{{ $t('覆盖模型的私有参数（不包含价格参数），可直接修改覆盖') }}
						</span>
						<div class="custom-config-editor__actions">
							<el-button
								size="small"
								type="primary"
								plain
								@click="syncFromModelConfig(scope)"
							>
								{{ $t('获取模型参数') }}
							</el-button>
							<el-button size="small" text @click="clearCustomConfig(scope)">
								{{ $t('清空') }}
							</el-button>
						</div>
					</div>
					<cl-editor-codemirror v-model="scope.customConfig" :height="180" />
				</div>
			</template>
		</cl-upsert>

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
						:preview-src-list="tester.imageItems.map((i) => i.src)"
						:initial-index="index"
						preview-teleported
					/>
					<el-button text type="primary" @click="copyText(item.value)">
						{{ $t('复制') }}
					</el-button>
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
	</cl-crud>
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

const modelTypeOptions = [
	{ label: t('对话'), value: 'chat', type: 'primary' },
	{ label: t('向量'), value: 'embedding', type: 'success' },
	{ label: t('图片'), value: 'image', type: 'warning' },
	{ label: t('音频'), value: 'audio', type: 'danger' },
	{ label: t('视频'), value: 'video', type: 'info' },
	{ label: t('重排'), value: 'rerank', type: 'success' }
];

const tester = reactive({
	visible: false,
	id: 0,
	modelType: '',
	prompt: '你好，请用一句话介绍你自己。',
	result: '',
	imageItems: [] as { src: string; value: string; url?: string }[]
});

/** 模型下拉数据（service.ai.model.list 行对象的宽松子集） */
interface ModelOption {
	id?: number;
	modelType?: string;
	name?: string;
	code?: string;
	defaultConfig?: string | null;
}

const modelsList = ref<ModelOption[]>([]);

onMounted(async () => {
	try {
		const res = await service.ai.model.list({});
		modelsList.value = res || [];
	} catch (e) {
		console.warn('加载模型列表失败:', e);
	}
});

function getModelType(scope: Record<string, unknown>): string {
	if (!scope) return '';
	if (scope.modelType) return String(scope.modelType);
	if (scope.modelId) {
		const mid = normalizeSingleId(scope.modelId);
		const m = modelsList.value.find((item) => item.id == mid);
		if (m) return m.modelType || '';
	}
	return '';
}

function isChatModel(scope: Record<string, unknown>): boolean {
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

function handleModelChange(val: unknown) {
	const mid = normalizeSingleId(val);
	if (!mid) return;
	const m = modelsList.value.find((item) => item.id == mid);
	if (!m) return;

	Upsert.value?.setForm('modelType', m.modelType || '');

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

	// 3. 若当前尚未配置私有参数，且所选模型有默认私有参数，自动带入
	const currentCustom = Upsert.value?.getForm('customConfig');
	if ((!currentCustom || !String(currentCustom).trim() || currentCustom === '{}') && m.defaultConfig) {
		try {
			const formatted = JSON.stringify(JSON.parse(m.defaultConfig), null, 2);
			Upsert.value?.setForm('customConfig', formatted);
		} catch {
			Upsert.value?.setForm('customConfig', m.defaultConfig);
		}
	}
}

function syncFromModelConfig(scope: Record<string, unknown>) {
	const mid = normalizeSingleId(scope?.modelId || Upsert.value?.getForm('modelId'));
	if (!mid) {
		ElMessage.warning(t('请先选择模型'));
		return;
	}
	const m = modelsList.value.find((item) => item.id == mid);
	if (!m) {
		ElMessage.warning(t('未找到所选模型信息'));
		return;
	}
	const configStr = m.defaultConfig;
	if (!configStr || !String(configStr).trim() || configStr === '{}') {
		ElMessage.info(t('该模型未配置私有默认参数'));
		scope.customConfig = '{}';
		Upsert.value?.setForm('customConfig', '{}');
		return;
	}
	try {
		const parsed = JSON.parse(configStr);
		const formatted = JSON.stringify(parsed, null, 2);
		scope.customConfig = formatted;
		Upsert.value?.setForm('customConfig', formatted);
		ElMessage.success(t('已成功获取模型私有参数配置'));
	} catch {
		scope.customConfig = configStr;
		Upsert.value?.setForm('customConfig', configStr);
		ElMessage.success(t('已成功获取模型私有参数配置'));
	}
}

function clearCustomConfig(scope: Record<string, unknown>) {
	scope.customConfig = '';
	Upsert.value?.setForm('customConfig', '');
}

function handleScenarioInput(scenVal: string) {
	const currentMid = normalizeSingleId(Upsert.value?.getForm('modelId'));
	const m = currentMid ? modelsList.value.find((item) => item.id == currentMid) : null;
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

// ---- Upsert 配置（标准 tabs 分组，消除虚假 prop，cool-crud-conventions.mdc） ----
const Upsert = useUpsert({
	dialog: { width: '840px' },
	props: { labelWidth: '120px' },
	items: [
		{
			type: 'tabs',
			props: {
				type: 'card',
				labels: [
					{ label: t('基本信息'), value: 'base' },
					{ label: t('推理参数'), value: 'params' },
					{ label: t('私有参数'), value: 'custom' },
					{ label: t('调度容灾'), value: 'schedule' },
					{ label: t('状态控制'), value: 'control' }
				]
			}
		},
		// --- 1. 基本信息 ---
		{
			label: t('模型'),
			prop: 'modelId',
			group: 'base',
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
					onChange(val: unknown) {
						handleModelChange(val);
					}
				}
			}
		},
		{
			label: t('场景'),
			prop: 'scenario',
			group: 'base',
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
			group: 'base',
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
			group: 'base',
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
			label: t('采样温度'),
			renderLabel: renderLabelWithTip(t('采样温度'), t('控制输出随机性，范围 0-2，精确任务建议调低')),
			prop: 'temperature',
			group: 'params',
			span: 8,
			hidden: ({ scope }) => !isChatModel(scope),
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
			group: 'params',
			span: 8,
			hidden: ({ scope }) => !isChatModel(scope),
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
			group: 'params',
			span: 8,
			hidden: ({ scope }) => !isChatModel(scope),
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
			group: 'params',
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
			group: 'params',
			span: 24,
			hidden: ({ scope }) => !isChatModel(scope),
			component: { name: 'cl-editor', props: { name: 'cl-editor-codemirror', height: 180 } }
		},

		// --- 3. 模型私有参数 ---
		{
			label: t('私有参数配置'),
			prop: 'customConfig',
			group: 'custom',
			span: 24,
			component: { name: 'slot-customConfig' }
		},

		// --- 4. 运行调度与容灾 ---
		{
			label: t('超时时间 (秒)'),
			renderLabel: renderLabelWithTip(t('超时时间 (秒)'), t('单次调用允许的最长等待时间')),
			prop: 'timeout',
			group: 'schedule',
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
			group: 'schedule',
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
			group: 'schedule',
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
			group: 'schedule',
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

		// --- 5. 状态与控制 ---
		{
			label: t('排序'),
			prop: 'orderNum',
			group: 'control',
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
			group: 'control',
			value: false,
			span: 8,
			component: { name: 'el-switch' }
		},
		{
			label: t('启用'),
			prop: 'status',
			group: 'control',
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
			const mid = normalizeSingleId(data.modelId);
			const m = modelsList.value.find((item) => item.id == mid);
			if (m) data.modelType = m.modelType;
		}

		if (data?.customConfig) {
			try {
				data.customConfig = JSON.stringify(JSON.parse(data.customConfig), null, 2);
			} catch {
				// 保持原样
			}
		} else if (!data?.id && data?.modelId) {
			const mid = normalizeSingleId(data.modelId);
			const m = modelsList.value.find((item) => item.id == mid);
			if (m?.defaultConfig) {
				try {
					data.customConfig = JSON.stringify(JSON.parse(m.defaultConfig), null, 2);
				} catch {
					data.customConfig = m.defaultConfig;
				}
			}
		}
	},
	onSubmit(data, { next }) {
		const payload = { ...data };
		if (!payload.code || !String(payload.code).trim()) {
			const currentMid = normalizeSingleId(payload.modelId);
			const m = currentMid ? modelsList.value.find((item) => item.id == currentMid) : null;
			const base = (m?.code || deriveProfileSlug(payload.name || '') || 'profile').toLowerCase().replace(/[^a-z0-9-_]/g, '-');
			const scen = String(payload.scenario || 'default').toLowerCase().replace(/[^a-z0-9-_]/g, '-');
			payload.code = `${base}-${scen}`.replace(/-+/g, '-').replace(/^-+|-+$/g, '');
		}
		// 非对话模型时，清理对话专用参数（置 null 触发后端显式清空更新）
		const type = getModelType(payload);
		if (type && type !== 'chat' && type !== 'llm') {
			payload.temperature = null;
			payload.topP = null;
			payload.maxTokens = null;
			payload.responseFormat = null;
			payload.toolsConfig = null;
		}
		// 校验并规范化 customConfig JSON 格式
		if (payload.customConfig && String(payload.customConfig).trim()) {
			try {
				const parsed = JSON.parse(payload.customConfig);
				if (typeof parsed !== 'object' || parsed === null || Array.isArray(parsed)) {
					ElMessage.error(t('模型私有参数必须为合法的 JSON 对象'));
					return;
				}
				payload.customConfig = JSON.stringify(parsed);
			} catch {
				ElMessage.error(t('模型私有参数 JSON 格式不正确，请检查'));
				return;
			}
		} else {
			payload.customConfig = null;
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
		{ type: 'selection', width: 60 },
		{ label: t('编码'), prop: 'code', minWidth: 160, hidden: true },
		{ label: t('名称'), prop: 'name', minWidth: 150 },
		{ label: t('场景'), prop: 'scenario', minWidth: 130 },
		{ label: t('模型'), prop: 'modelName', minWidth: 160 },
		{
			label: t('类型'),
			prop: 'modelType',
			minWidth: 110,
			dict: modelTypeOptions,
			dictColor: true
		},
		{ label: t('厂商'), prop: 'providerName', minWidth: 140 },
		{
			label: t('默认'),
			prop: 'isDefault',
			width: 90,
			dict: [
				{ label: t('默认'), value: true, type: 'success' },
				{ label: t('否'), value: false, type: 'info' }
			],
			dictColor: true
		},
		{ label: t('启用'), prop: 'status', width: 90, component: { name: 'cl-switch' } },
		{ label: t('创建时间'), prop: 'createTime', sortable: 'desc', minWidth: 170, component: { name: 'cl-date-text' } },
		{
			type: 'op',
			width: 280,
			fixed: 'right',
			buttons: ['edit', 'delete', 'slot-default', 'slot-test']
		}
	],
	contextMenu: ['refresh', 'check', 'edit', 'delete']
});

const Crud = useCrud(
	{
		service: service.ai.profile
	},
	(app) => {
		app.refresh();
	}
);

async function setDefault(row: { id: number }) {
	await service.ai.profile.setDefault({ id: row.id });
	ElMessage.success(t('设置成功'));
	Crud.value?.refresh();
}

function openTest(row: { id: number; modelType?: string }) {
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
	} catch (err) {
		ElMessage.error((err as Error).message || t('调用失败'));
	}
}

function normalizeSingleId(value: unknown) {
	return Array.isArray(value) ? value[0] : value;
}

function copyText(val: string) {
	if (!val) return;
	navigator.clipboard.writeText(val);
	ElMessage.success(t('已复制'));
}
</script>

<style lang="scss" scoped>
.custom-config-editor {
	width: 100%;

	&__tools {
		display: flex;
		align-items: center;
		justify-content: space-between;
		margin-bottom: 8px;
		color: var(--el-text-color-secondary);
		font-size: 13px;
	}

	&__hint {
		font-size: 12px;
		color: var(--el-text-color-secondary);
	}

	&__actions {
		display: flex;
		align-items: center;
		gap: 8px;
	}
}

.label-with-tip {
	display: inline-flex;
	align-items: center;
}

.label-tip-icon {
	color: var(--el-text-color-secondary);
	margin-left: 4px;
	cursor: pointer;
}

.test-images {
	display: flex;
	flex-wrap: wrap;
	gap: 12px;
	margin-top: 16px;
}

.test-image {
	width: 120px;
	text-align: center;

	.el-image {
		width: 120px;
		height: 120px;
		border-radius: 4px;
		border: 1px solid var(--el-border-color-lighter);
	}
}

.result {
	margin-top: 16px;
}
</style>
