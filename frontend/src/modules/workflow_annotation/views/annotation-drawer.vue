<template>
	<el-drawer
		:model-value="visible"
		:title="$t('标注用例')"
		size="540px"
		:close-on-click-modal="false"
		@update:model-value="emit('update:visible', $event)"
	>
		<!-- 队列模式快捷键提示 -->
		<div v-if="isQueueMode" class="ann-shortcut">
			<el-text type="info" size="small">
				{{ $t('快捷键：P=Pass  F=Fail  J/→=下一条  K/←=上一条  Enter=提交并下一条') }}
			</el-text>
		</div>

		<!-- 上下文（只读）：输入 / 输出 / 期望 / Judge 评分 -->
		<div class="ann-context">
			<div class="ann-section-title">{{ $t('上下文') }}</div>
			<div v-if="pretty(currentContext.inputData)" class="ann-field">
				<div class="ann-label">{{ $t('输入') }}</div>
				<pre class="ann-pre">{{ pretty(currentContext.inputData) }}</pre>
			</div>
			<div v-if="pretty(currentContext.actualOutput)" class="ann-field">
				<div class="ann-label">{{ $t('实际输出') }}</div>
				<pre class="ann-pre">{{ pretty(currentContext.actualOutput) }}</pre>
			</div>
			<div v-if="pretty(currentContext.expectedOutput)" class="ann-field">
				<div class="ann-label">{{ $t('期望输出') }}</div>
				<pre class="ann-pre">{{ pretty(currentContext.expectedOutput) }}</pre>
			</div>
			<div class="ann-field">
				<div class="ann-label">{{ $t('Judge 评分') }}</div>
				<div class="ann-judge">
					<b>{{ Number(currentContext.score ?? 0).toFixed(2) }}</b>
					<el-tag :type="currentContext.passed ? 'success' : 'danger'" size="small">
						{{ currentContext.passed ? $t('通过') : $t('失败') }}
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
						<el-icon class="ann-help"><info-filled /></el-icon>
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
			<template v-if="isQueueMode">
				<el-button :disabled="currentIndex <= 0" @click="goPrev">{{ $t('上一条') }}</el-button>
				<span class="ann-pager">{{ currentIndex + 1 }} / {{ total }}</span>
				<el-button :disabled="currentIndex >= total - 1" @click="goNext">{{ $t('下一条') }}</el-button>
			</template>
			<cl-flex1 />
			<el-button @click="emit('update:visible', false)">{{ $t('取消') }}</el-button>
			<el-button v-if="isQueueMode" type="primary" :loading="submitting" @click="submitAndNext">{{ $t('提交并下一条') }}</el-button>
			<el-button v-else type="primary" :loading="submitting" @click="submit()">{{ $t('提交') }}</el-button>
		</div>
	</template>
	</el-drawer>
</template>

<script lang="ts" setup>
defineOptions({ name: 'workflow-annotation-drawer' });

import { computed, onBeforeUnmount, reactive, ref, watch } from 'vue';
import { ElMessage } from 'element-plus';
import { InfoFilled } from '@element-plus/icons-vue';
import { useCool } from '/@/cool';
import { useI18n } from 'vue-i18n';
import { pretty, parseJudgeDetail } from '../utils/format';

interface CaseContext {
	inputData?: string | null;
	actualOutput?: string | null;
	expectedOutput?: string | null;
	score?: number | null;
	passed?: boolean;
	evaluatorDetail?: string | null;
}

// 队列模式传入的用例结果行（结构对齐 run.vue 中 detail.cases 的行）
interface WorkflowEvalCaseResult {
	id?: number;
	caseResultId?: number;
	inputData?: string | null;
	actualOutput?: string | null;
	expectedOutput?: string | null;
	score?: number | null;
	passed?: boolean;
	evaluatorDetail?: string | null;
	[key: string]: any;
}

const props = defineProps<{
	visible: boolean;
	// 单条模式（向后兼容）
	caseResultId?: number;
	context?: CaseContext;
	// 队列模式
	caseResults?: WorkflowEvalCaseResult[];
	initialIndex?: number;
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

// 队列模式状态
const isQueueMode = computed(() => Array.isArray(props.caseResults) && props.caseResults.length > 0);
const total = computed(() => props.caseResults?.length || 0);
const currentIndex = ref<number>(props.initialIndex || 0);

const currentCase = computed<WorkflowEvalCaseResult | null>(() => {
	if (!isQueueMode.value) return null;
	return props.caseResults![currentIndex.value] || null;
});

// 当前用例的 caseResultId：队列模式从 currentCase 取，否则回退原 prop
const currentCaseResultId = computed<number>(() => {
	if (isQueueMode.value && currentCase.value) {
		return Number(currentCase.value.caseResultId || currentCase.value.id || 0);
	}
	return Number(props.caseResultId || 0);
});

// 当前用例上下文：队列模式从 currentCase 提取，否则用原 prop
const currentContext = computed<CaseContext>(() => {
	if (isQueueMode.value && currentCase.value) {
		return {
			inputData: currentCase.value.inputData,
			actualOutput: currentCase.value.actualOutput,
			expectedOutput: currentCase.value.expectedOutput,
			score: currentCase.value.score,
			passed: currentCase.value.passed,
			evaluatorDetail: currentCase.value.evaluatorDetail
		};
	}
	return props.context || {};
});

const judgeDetail = computed(() => parseJudgeDetail(currentContext.value?.evaluatorDetail));

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
	const caseResultId = currentCaseResultId.value;
	if (!caseResultId) return;
	try {
		const res = await annService.page({ caseResultId, size: 1 });
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
		if (v) {
			// 打开时按 initialIndex 对齐索引，再加载已有标注
			if (isQueueMode.value) {
				currentIndex.value = Math.min(props.initialIndex || 0, total.value - 1);
			}
			loadExisting();
			window.addEventListener('keydown', onKeyDown);
		} else {
			window.removeEventListener('keydown', onKeyDown);
		}
	}
);

// 队列模式切换索引：重新加载该用例的已有标注
watch(currentIndex, () => {
	if (isQueueMode.value && props.visible) {
		loadExisting();
	}
});

// 队列数据变化时重置索引（避免越界）
watch(
	() => props.caseResults,
	() => {
		if (isQueueMode.value) {
			currentIndex.value = Math.min(props.initialIndex || 0, total.value - 1);
		}
	}
);

// 队列导航
function goNext() {
	if (currentIndex.value < total.value - 1) {
		currentIndex.value++;
	}
}
function goPrev() {
	if (currentIndex.value > 0) {
		currentIndex.value--;
	}
}

// 提交：closeAfter 控制是否关闭抽屉；队列模式下始终由调用方决定
async function submit(closeAfter = true): Promise<boolean> {
	submitting.value = true;
	try {
		const caseResultId = currentCaseResultId.value;
		const fields = {
			label: form.label,
			score: form.score,
			reason: form.reason,
			isGold: form.isGold
		};
		if (mode.value === 'update' && annotationId.value) {
			await annService.update({ id: annotationId.value, ...fields });
		} else {
			await annService.add({ caseResultId, ...fields });
		}
		ElMessage.success(t('已保存'));
		emit('saved');
		if (closeAfter && !isQueueMode.value) {
			emit('update:visible', false);
		}
		return true;
	} catch (e: any) {
		ElMessage.error(e?.message || t('保存失败'));
		return false;
	} finally {
		submitting.value = false;
	}
}

// 提交并跳下一条；已是最后一条则提示并关闭
async function submitAndNext() {
	const ok = await submit(false);
	if (!ok) return;
	if (currentIndex.value < total.value - 1) {
		goNext();
	} else {
		ElMessage.success(t('已完成全部标注'));
		emit('update:visible', false);
	}
}

// 键盘快捷键（仅队列模式生效）：P/F 切换标注，J/→ 下一条，K/← 上一条，Enter 提交并下一条
function onKeyDown(e: KeyboardEvent) {
	if (!props.visible || !isQueueMode.value) return;
	const tag = (document.activeElement?.tagName || '').toLowerCase();
	const isInput = tag === 'input' || tag === 'textarea' || (document.activeElement as HTMLElement)?.isContentEditable;

	if (e.key === 'Enter' && !isInput) {
		e.preventDefault();
		submitAndNext();
		return;
	}
	if (e.key === 'Enter' && tag === 'textarea') {
		// textarea 中 Enter 换行，不拦截
		return;
	}
	if (isInput) return; // 输入框中单字母快捷键不触发

	switch (e.key.toLowerCase()) {
		case 'p':
			form.label = 'pass';
			onLabelChange('pass');
			break;
		case 'f':
			form.label = 'fail';
			onLabelChange('fail');
			break;
		case 'j':
		case 'arrowright':
			e.preventDefault();
			goNext();
			break;
		case 'k':
		case 'arrowleft':
			e.preventDefault();
			goPrev();
			break;
	}
}

onBeforeUnmount(() => {
	window.removeEventListener('keydown', onKeyDown);
});
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
.ann-shortcut {
	margin-bottom: 8px;
	padding: 4px 8px;
	background: var(--el-fill-color-light);
	border-radius: 4px;
}
.ann-pager {
	margin: 0 8px;
	font-size: 13px;
	color: var(--el-text-color-regular);
	white-space: nowrap;
}
</style>
