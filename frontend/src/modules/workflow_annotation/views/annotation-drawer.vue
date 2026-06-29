<template>
	<el-drawer
		:model-value="visible"
		:title="$t('标注用例')"
		size="540px"
		:close-on-click-modal="false"
		@update:model-value="emit('update:visible', $event)"
	>
		<!-- 上下文（只读）：输入 / 输出 / 期望 / Judge 评分 -->
		<div class="ann-context">
			<div class="ann-section-title">{{ $t('上下文') }}</div>
			<div v-if="pretty(context.inputData)" class="ann-field">
				<div class="ann-label">{{ $t('输入') }}</div>
				<pre class="ann-pre">{{ pretty(context.inputData) }}</pre>
			</div>
			<div v-if="pretty(context.actualOutput)" class="ann-field">
				<div class="ann-label">{{ $t('实际输出') }}</div>
				<pre class="ann-pre">{{ pretty(context.actualOutput) }}</pre>
			</div>
			<div v-if="pretty(context.expectedOutput)" class="ann-field">
				<div class="ann-label">{{ $t('期望输出') }}</div>
				<pre class="ann-pre">{{ pretty(context.expectedOutput) }}</pre>
			</div>
			<div class="ann-field">
				<div class="ann-label">{{ $t('Judge 评分') }}</div>
				<div class="ann-judge">
					<b>{{ Number(context.score ?? 0).toFixed(2) }}</b>
					<el-tag :type="context.passed ? 'success' : 'danger'" size="small">
						{{ context.passed ? $t('通过') : $t('失败') }}
					</el-tag>
					<span v-if="judgeDetail?.reason" class="ann-judge-reason">{{ judgeDetail.reason }}</span>
				</div>
			</div>
		</div>

		<!-- 标注表单：二元判断为主交互，分数/理由折叠为高级选项 -->
		<el-form :model="form" label-width="90px" class="ann-form">
			<el-form-item :label="$t('标注')" required>
				<el-radio-group v-model="form.label" size="default" @change="onLabelChange">
					<el-radio-button value="pass">👍 {{ $t('通过') }}</el-radio-button>
					<el-radio-button value="fail">👎 {{ $t('失败') }}</el-radio-button>
				</el-radio-group>
			</el-form-item>

			<el-collapse>
				<el-collapse-item :title="$t('高级选项（分数 / 理由）')" name="adv">
					<el-form-item :label="$t('分数')">
						<el-slider v-model="form.score" :min="0" :max="1" :step="0.05" show-stops />
					</el-form-item>
					<el-form-item :label="$t('理由')">
						<el-input
							v-model="form.reason"
							type="textarea"
							:rows="3"
							maxlength="500"
							show-word-limit
							:placeholder="$t('可选：说明判断依据')"
						/>
					</el-form-item>
				</el-collapse-item>
			</el-collapse>

			<el-form-item>
				<template #label>
					<span>{{ $t('金标准') }}</span>
					<el-tooltip
						:content="$t('标记后该结果将纳入评测基准集，用于自动化评测对比。请谨慎标记。')"
						placement="top"
					>
						<el-icon class="ann-help"><InfoFilled /></el-icon>
					</el-tooltip>
				</template>
				<el-switch v-model="form.isGold" />
			</el-form-item>
		</el-form>

		<template #footer>
			<div class="ann-footer">
				<span v-if="existingInfo" class="ann-existing">
					{{ $t('已有标注') }}（ID {{ existingInfo.id }}{{ existingInfo.annotatorUserId ? `，${$t('标注人')} ${existingInfo.annotatorUserId}` : '' }}）
				</span>
				<cl-flex1 />
				<el-button @click="emit('update:visible', false)">{{ $t('取消') }}</el-button>
				<el-button type="primary" :loading="submitting" @click="submit">{{ $t('提交') }}</el-button>
			</div>
		</template>
	</el-drawer>
</template>

<script lang="ts" setup>
defineOptions({ name: 'workflow-annotation-drawer' });

import { computed, reactive, ref, watch } from 'vue';
import { ElMessage } from 'element-plus';
import { InfoFilled } from '@element-plus/icons-vue';
import { useCool } from '/@/cool';
import { useI18n } from 'vue-i18n';

interface CaseContext {
	inputData?: string | null;
	actualOutput?: string | null;
	expectedOutput?: string | null;
	score?: number | null;
	passed?: boolean;
	evaluatorDetail?: string | null;
}

const props = defineProps<{
	visible: boolean;
	caseResultId: number;
	context: CaseContext;
}>();

const emit = defineEmits<{
	'update:visible': [boolean];
	saved: [];
}>();

const { service } = useCool();
const { t } = useI18n();
const annService = (service as any).workflow_annotation.annotation;

const form = reactive({
	label: 'pass',
	score: 1,
	reason: '',
	isGold: false
});
const submitting = ref(false);
const annotationId = ref<number | null>(null);
const existingInfo = ref<any>(null);
const mode = ref<'add' | 'update'>('add');

const judgeDetail = computed(() => parseJudgeDetail(props.context?.evaluatorDetail));

// JSON 字段美化展示（inputData / actualOutput 等都是 JSON 字符串快照）
function pretty(s: any): string {
	if (s === null || s === undefined || s === '') return '';
	try {
		const obj = typeof s === 'string' ? JSON.parse(s) : s;
		return typeof obj === 'string' ? obj : JSON.stringify(obj, null, 2);
	} catch {
		return String(s);
	}
}

function parseJudgeDetail(s: any): any {
	if (!s) return null;
	try {
		return typeof s === 'string' ? JSON.parse(s) : s;
	} catch {
		return null;
	}
}

function resetForm() {
	form.label = 'pass';
	form.score = 1;
	form.reason = '';
	form.isGold = false;
	annotationId.value = null;
	existingInfo.value = null;
}

// 二元判断切换时，分数默认跟随（pass→1 / fail→0），用户可在高级选项微调
function onLabelChange(v: string | number | boolean | undefined) {
	form.score = v === 'pass' ? 1 : 0;
}

// 打开抽屉时按 caseResultId 回显已有标注（gold 优先已在后端 page 排序外，这里取最新一条）
async function loadExisting() {
	resetForm();
	if (!props.caseResultId) return;
	try {
		const res = await annService.page({ caseResultId: props.caseResultId, size: 1 });
		const existing = res?.list?.[0];
		if (existing) {
			form.label = existing.label || 'pass';
			form.score = typeof existing.score === 'number' ? existing.score : existing.label === 'fail' ? 0 : 1;
			form.reason = existing.reason || '';
			form.isGold = !!existing.isGold;
			annotationId.value = existing.id;
			existingInfo.value = existing;
			mode.value = 'update';
		} else {
			mode.value = 'add';
		}
	} catch {
		mode.value = 'add';
	}
}

watch(
	() => props.visible,
	(v) => {
		if (v) loadExisting();
	}
);

async function submit() {
	submitting.value = true;
	try {
		const fields = {
			label: form.label,
			score: form.score,
			reason: form.reason,
			isGold: form.isGold
		};
		if (mode.value === 'update' && annotationId.value) {
			await annService.update({ id: annotationId.value, ...fields });
		} else {
			await annService.add({ caseResultId: props.caseResultId, ...fields });
		}
		ElMessage.success(t('已保存'));
		emit('saved');
		emit('update:visible', false);
	} catch (e: any) {
		ElMessage.error(e?.message || t('保存失败'));
	} finally {
		submitting.value = false;
	}
}
</script>

<style lang="scss" scoped>
.ann-context {
	margin-bottom: 12px;
	padding-bottom: 12px;
	border-bottom: 1px solid var(--el-border-color-lighter);
}
.ann-section-title {
	font-weight: 600;
	margin-bottom: 8px;
	color: var(--el-text-color-primary);
}
.ann-field {
	margin-bottom: 10px;
}
.ann-label {
	font-size: 12px;
	color: var(--el-text-color-secondary);
	margin-bottom: 4px;
}
.ann-pre {
	margin: 0;
	padding: 8px;
	max-height: 180px;
	overflow: auto;
	background: var(--el-fill-color-light);
	border-radius: 4px;
	font-size: 12px;
	white-space: pre-wrap;
	word-break: break-word;
}
.ann-judge {
	display: flex;
	align-items: center;
	gap: 8px;
}
.ann-judge-reason {
	color: var(--el-text-color-secondary);
	font-size: 12px;
}
.ann-form {
	padding-top: 4px;
}
.ann-help {
	margin-left: 4px;
	color: var(--el-text-color-secondary);
	cursor: help;
}
.ann-footer {
	display: flex;
	align-items: center;
	width: 100%;
}
.ann-existing {
	color: var(--el-text-color-secondary);
	font-size: 12px;
}
</style>
