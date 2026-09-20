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
					<el-button text type="primary" @click="setDefault(scope.row)">{{
						$t('设默认')
					}}</el-button>
				</template>

				<template #slot-test="{ scope }">
					<el-button text type="primary" @click="openTest(scope.row)">{{
						$t('测试')
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
import { h, markRaw, reactive } from 'vue';
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
					dict: { text: 'name' },
					columns: [
						{ label: t('厂商'), prop: 'providerName', minWidth: 140 },
						{ label: t('编码'), prop: 'code', minWidth: 160 },
						{ label: t('类型'), prop: 'modelType', minWidth: 110 }
					]
				}
			}
		},
		{
			label: t('场景'),
			prop: 'scenario',
			value: 'default',
			required: true,
			component: { name: 'el-input' }
		},
		{
			label: t('采样温度'),
			renderLabel: renderLabelWithTip(t('采样温度'), t('控制输出随机性，范围 0-2，精确任务建议调低')),
			prop: 'temperature',
			component: { name: 'el-input-number', props: { min: 0, max: 2, step: 0.1 } }
		},
		{
			label: t('核采样 (Top-P)'),
			renderLabel: renderLabelWithTip(
				t('核采样 (Top-P)'),
				t('仅保留累计概率前 P 的词元，值越小输出越确定')
			),
			prop: 'topP',
			component: { name: 'el-input-number', props: { min: 0, max: 1, step: 0.05 } }
		},
		{
			label: t('单次最大 Token'),
			renderLabel: renderLabelWithTip(t('单次最大 Token'), t('限制单次回复生成的最大 Token 数')),
			prop: 'maxTokens',
			component: { name: 'el-input-number' }
		},
		{
			label: t('响应格式'),
			prop: 'responseFormat',
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
			component: { name: 'cl-editor', props: { name: 'cl-editor-codemirror', height: 200 } }
		},
		{
			label: t('超时时间 (秒)'),
			renderLabel: renderLabelWithTip(t('超时时间 (秒)'), t('单次调用允许的最长等待时间')),
			prop: 'timeout',
			component: { name: 'el-input-number', props: { min: 1, 'controls-position': 'right' } }
		},
		{
			label: t('重试次数'),
			renderLabel: renderLabelWithTip(t('重试次数'), t('调用失败后自动重试的次数上限')),
			prop: 'retryCount',
			value: 0,
			component: {
				name: 'el-input-number',
				props: { min: 0, max: 5, 'controls-position': 'right' }
			}
		},
		{
			label: t('重试间隔 (秒)'),
			renderLabel: renderLabelWithTip(t('重试间隔 (秒)'), t('两次重试之间的等待时间')),
			prop: 'retryDelaySeconds',
			value: 0,
			component: {
				name: 'el-input-number',
				props: { min: 0, max: 60, 'controls-position': 'right' }
			}
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
	onSubmit(data, { next }) {
		next({
			...data,
			modelId: normalizeSingleId(data.modelId),
			// text 模式下编辑器产出空串，保持与旧行为一致：不提交该字段
			responseFormat: data.responseFormat || undefined
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
</style>
