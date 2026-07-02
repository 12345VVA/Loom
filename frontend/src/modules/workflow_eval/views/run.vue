<template>
	<cl-crud ref="Crud">
		<cl-row>
			<cl-refresh-btn />
			<el-button type="success" @click="openStartDialog">{{ $t('发起新评估') }}</el-button>
			<el-button
				type="warning"
				:disabled="selectedRuns.length !== 2"
				@click="goCompare"
			>{{ $t('回归对比(选2个)') }}</el-button
			>
			<el-button
				type="primary"
				:disabled="selectedRuns.length < 2"
				@click="goTrend"
			>{{ $t('趋势对比(选≥2个)') }}</el-button
			>
			<cl-flex1 />
			<cl-search-key :placeholder="$t('搜索版本号')" />
		</cl-row>

		<cl-row>
			<cl-table ref="Table" @selection-change="onSelectionChange">
				<template #slot-status="{ scope }">
					<el-tag :type="statusTagType(scope.row.status)" size="small">{{ statusLabel(scope.row.status) }}</el-tag>
				</template>
				<template #slot-detail="{ scope }">
					<el-button text type="primary" @click="openDetail(scope.row)">{{ $t('详情') }}</el-button>
				</template>
				<template #slot-cancel="{ scope }">
					<el-button
						text
						type="danger"
						:disabled="!['pending', 'running'].includes(scope.row.status)"
						@click="cancelRun(scope.row)"
					>{{ $t('取消') }}</el-button
					>
				</template>
			</cl-table>
		</cl-row>

		<cl-row>
			<cl-flex1 />
			<cl-pagination />
		</cl-row>
	</cl-crud>

	<!-- 发起评估对话框 -->
	<el-dialog v-model="startDialog.visible" :title="$t('发起新评估')" width="520px">
		<el-form label-width="110px">
			<el-form-item :label="$t('测试集')" required>
				<el-select v-model="startDialog.form.testSetId" :placeholder="$t('选择测试集')" filterable>
					<el-option
						v-for="ts in testSetOptions"
						:key="ts.id"
						:label="`${ts.name} (${ts.itemsCount}例)`"
						:value="ts.id"
					/>
				</el-select>
			</el-form-item>
			<el-form-item :label="$t('工作流(可选)')">
				<el-select
					v-model="startDialog.form.definitionId"
					:placeholder="$t('缺省用测试集关联的')"
					filterable
					clearable
					@change="onDefinitionChange"
				>
					<el-option
						v-for="d in definitionOptions"
						:key="d.id"
						:label="d.name"
						:value="d.id"
					/>
				</el-select>
			</el-form-item>
			<el-form-item :label="$t('版本(可选)')">
				<el-select
					v-model="startDialog.form.definitionVersionId"
					:placeholder="$t('缺省取当前发布版')"
					filterable
					clearable
					:disabled="!startDialog.form.definitionId"
				>
					<el-option
						v-for="v in versionOptions"
						:key="v.id"
						:label="`${formatVersionNo(v.versionNo)} (${versionStatusLabel(v.status)})`"
						:value="v.id"
					/>
				</el-select>
			</el-form-item>
			<el-form-item :label="$t('版本号')">
				<el-input v-model="startDialog.form.versionLabel" :placeholder="$t('如 v1.2 / commit hash')" />
			</el-form-item>
			<el-form-item :label="$t('评估器')">
				<el-select v-model="startDialog.form.evaluatorType">
					<el-option :label="$t('规则匹配')" value="rule_match" />
					<el-option :label="$t('LLM 评分')" value="llm_judge" />
					<el-option :label="$t('组合')" value="composite" />
					<el-option :label="$t('JSON 结构')" value="json_schema" />
					<el-option :label="$t('安全(PII)')" value="safety" />
				</el-select>
			</el-form-item>
		</el-form>
		<template #footer>
			<el-button @click="startDialog.visible = false">{{ $t('取消') }}</el-button>
			<el-button type="primary" :loading="startDialog.loading" @click="submitStart">{{ $t('发起') }}</el-button>
		</template>
	</el-dialog>

	<!-- 运行详情抽屉 -->
	<el-drawer v-model="detail.visible" :title="$t('评估运行详情')" size="900px">
		<el-descriptions v-if="detail.run" :column="3" border class="detail-summary">
			<el-descriptions-item :label="$t('状态')">
				<el-tag :type="statusTagType(detail.run.status)" size="small">{{ statusLabel(detail.run.status) }}</el-tag>
			</el-descriptions-item>
			<el-descriptions-item :label="$t('通过率')">{{ ((detail.run.passRate ?? 0) * 100).toFixed(1) }}%</el-descriptions-item>
			<el-descriptions-item :label="$t('平均分')">{{ (detail.run.avgScore ?? 0).toFixed(3) }}</el-descriptions-item>
			<el-descriptions-item :label="$t('总数/通过/失败/异常')">
				{{ detail.run.total }} / {{ detail.run.passed }} / {{ detail.run.failed }} / {{ detail.run.errored }}
			</el-descriptions-item>
			<el-descriptions-item :label="$t('P95 延迟')">{{ detail.run.p95LatencyMs ?? 0 }}ms</el-descriptions-item>
			<el-descriptions-item>
				<template #label>
					<el-tooltip :content="$t('按本次评估关联的工作流实例精确聚合')" placement="top">
						<span>{{ $t('Token/成本') }}</span>
					</el-tooltip>
				</template>
				{{ detail.run.totalTokens ?? 0 }} / ${{ ((detail.run.totalCostMicroUsd ?? 0) / 1e6).toFixed(4) }}
			</el-descriptions-item>
		</el-descriptions>

		<el-card class="kappa-card">
			<template #header>{{ $t('Judge 校准（人工标注 Cohen\'s κ）') }}</template>
			<el-button type="primary" :loading="kappaLoading" @click="computeKappa">{{ $t('计算 κ') }}</el-button>
			<span v-if="kappaResult" class="kappa-result">
				κ = <b>{{ kappaResult.kappa ?? '-' }}</b>
				<el-tag :type="kappaLevelType(kappaResult.level)" size="small" style="margin: 0 8px">{{ kappaLevelLabel(kappaResult.level) }}</el-tag>
				<span style="color: #999">n={{ kappaResult.n }}，{{ $t('一致率') }} {{ ((kappaResult.agreementRate ?? 0) * 100).toFixed(1) }}%</span>
			</span>
		</el-card>

		<el-table :data="detail.cases" border style="margin-top: 16px">
			<el-table-column type="expand">
				<template #default="{ row }">
					<div v-if="parseJudgeDetail(row.evaluatorDetail)" class="judge-detail">
						<div v-if="parseJudgeDetail(row.evaluatorDetail).reason" class="judge-reason">
							<b>{{ $t('评分理由') }}：</b>{{ parseJudgeDetail(row.evaluatorDetail).reason }}
						</div>
						<div
							v-if="parseJudgeDetail(row.evaluatorDetail).dimensions"
							class="judge-dims"
						>
							<b>{{ $t('维度评分') }}：</b>
							<el-tag
								v-for="(v, k) in parseJudgeDetail(row.evaluatorDetail).dimensions"
								:key="k"
								size="small"
								style="margin-right: 8px"
							>{{ k }}: {{ Number(v).toFixed(2) }}</el-tag>
						</div>
						<div
							v-if="parseJudgeDetail(row.evaluatorDetail).node_results?.length"
							class="judge-dims"
						>
							<b>{{ $t('节点评估(trace)') }}：</b>
							<div
								v-for="nr in parseJudgeDetail(row.evaluatorDetail).node_results"
								:key="nr.node_id"
								style="margin-left: 8px"
							>
								<el-tag :type="nr.passed ? 'success' : 'danger'" size="small">{{ nr.node_id }}</el-tag>
								<span style="margin-left: 4px">{{ Number(nr.score ?? 0).toFixed(2) }}</span>
								<span v-if="nr.reason" style="color: #999; margin-left: 4px">{{ nr.reason }}</span>
							</div>
						</div>
					</div>
					<span v-else style="color: #999">{{ $t('无评分详情') }}</span>
				</template>
			</el-table-column>
			<el-table-column prop="caseKey" :label="$t('用例')" min-width="120" />
			<el-table-column prop="status" :label="$t('状态')" width="90">
				<template #default="{ row }">
					<el-tag :type="caseStatusType(row.status)" size="small">{{ row.status }}</el-tag>
				</template>
			</el-table-column>
			<el-table-column prop="score" :label="$t('得分')" width="80" />
			<el-table-column prop="latencyMs" :label="$t('耗时(ms)')" width="100" />
			<el-table-column prop="actualOutput" :label="$t('实际输出')" min-width="220" show-overflow-tooltip />
			<el-table-column prop="errorMessage" :label="$t('错误')" min-width="160" show-overflow-tooltip />
			<el-table-column :label="$t('操作')" width="80" fixed="right">
				<template #default="{ row }">
					<el-button text type="primary" @click="openAnnotation(row)">{{ $t('标注') }}</el-button>
				</template>
			</el-table-column>
		</el-table>
		<div class="detail-pager">
			<el-pagination
				background
				layout="prev, pager, next"
				:total="detail.total"
				:page-size="detail.size"
				:current-page="detail.page"
				@current-change="onDetailPage"
			/>
		</div>
	</el-drawer>

	<annotation-drawer
	v-model:visible="annotation.visible"
	:case-result-id="annotation.caseResultId"
	:context="annotation.context"
	:case-results="annotationQueue"
	:initial-index="annotationInitialIndex"
	@saved="loadCases"
/>
</template>

<script lang="ts" setup>
defineOptions({ name: 'workflow-eval-run' });

import { useCrud, useTable } from '@cool-vue/crud';
import { ElMessage, ElMessageBox } from 'element-plus';
import { reactive, ref } from 'vue';
import { useCool } from '/@/cool';
import { useI18n } from 'vue-i18n';
import { useRouter } from 'vue-router';
import AnnotationDrawer from '/$/workflow_annotation/views/annotation-drawer.vue';
import { formatVersionNo } from '/$/workflow/utils';
import { statusTagType, caseStatusType, kappaLevelType, parseJudgeDetail } from '../utils/format';

const { service } = useCool();
const { t } = useI18n();
const router = useRouter();
const evalService = (service as any).workflow_eval;

const testSetOptions = ref<any[]>([]);
const definitionOptions = ref<any[]>([]);
(async () => {
	try {
		const [ts, defs] = await Promise.all([
			evalService.test_set.list(),
			(service as any).workflow.definition.list()
		]);
		testSetOptions.value = ts || [];
		definitionOptions.value = defs || [];
	} catch (e) {
		// ignore
		console.warn('[workflow_eval/run] 拉取 test_set + definition 失败', e);
	}
})();

// 版本下拉：选 definition 后拉其版本列表（缺省取当前发布版）
const versionOptions = ref<any[]>([]);
function versionStatusLabel(s: string) {
	return { draft: t('草稿'), published: t('已发布'), archived: t('已归档') }[s] || s;
}
async function onDefinitionChange() {
	startDialog.form.definitionVersionId = null;
	versionOptions.value = [];
	if (!startDialog.form.definitionId) return;
	try {
		const res = await (service as any).workflow.version.page({
			definitionId: startDialog.form.definitionId,
			size: 50
		});
		versionOptions.value = res.list || [];
	} catch (e) {
		// ignore
	}
}

const Crud = useCrud({ service: evalService.eval_run }, (app) => app.refresh());

const selectedRuns = ref<any[]>([]);
function onSelectionChange(rows: any[]) {
	selectedRuns.value = rows;
}

const Table = useTable({
	columns: [
		{ type: 'selection' },
		{ label: t('版本号'), prop: 'versionLabel', minWidth: 120 },
		{ label: t('状态'), prop: 'status', minWidth: 100 },
		{ label: t('通过率'), prop: 'passRate', width: 90 },
		{ label: t('平均分'), prop: 'avgScore', width: 90 },
		{ label: t('P95(ms)'), prop: 'p95LatencyMs', width: 90 },
		{ label: t('总数'), prop: 'total', width: 70 },
		{ label: t('创建时间'), prop: 'createTime', minWidth: 170, sortable: 'desc' },
		{ type: 'op', buttons: ['slot-detail', 'slot-cancel'], width: 140 }
	]
});

function statusLabel(s: string) {
	return { pending: t('等待'), running: t('运行中'), succeeded: t('成功'), failed: t('失败'), partial: t('部分成功'), cancelled: t('已取消') }[s] || s;
}

// judge 校准 κ：调标注模块计算 judge 与人工标注的 Cohen's κ
const kappaLoading = ref(false);
const kappaResult = ref<any>(null);
async function computeKappa() {
	if (!detail.runId) return;
	kappaLoading.value = true;
	try {
		kappaResult.value = await (service as any).workflow_annotation.annotation.kappa({ evalRunId: detail.runId });
	} catch (e: any) {
		ElMessage.error(e?.message || e);
	} finally {
		kappaLoading.value = false;
	}
}
function kappaLevelLabel(level: string) {
	return {
		reliable: t('可信(≥0.6)'),
		moderate: t('中等(0.4-0.6)'),
		unreliable: t('不可信(<0.4)'),
		no_annotation: t('无标注')
	}[level] || level;
}

// 发起评估
const startDialog = reactive<{ visible: boolean; loading: boolean; form: any }>({
	visible: false,
	loading: false,
	form: { testSetId: null, definitionId: null, definitionVersionId: null, versionLabel: '', evaluatorType: 'rule_match' }
});
function openStartDialog() {
	startDialog.form = { testSetId: null, definitionId: null, definitionVersionId: null, versionLabel: '', evaluatorType: 'rule_match' };
	versionOptions.value = [];
	startDialog.visible = true;
}
async function submitStart() {
	if (!startDialog.form.testSetId) {
		ElMessage.warning(t('请选择测试集'));
		return;
	}
	startDialog.loading = true;
	try {
		await evalService.eval_run.start(startDialog.form);
		ElMessage.success(t('评估已发起'));
		startDialog.visible = false;
		Crud.value?.refresh();
	} catch (err: any) {
		ElMessage.error(`${t('发起失败')}: ${err.message || err}`);
	} finally {
		startDialog.loading = false;
	}
}

async function cancelRun(row: any) {
	try {
		await ElMessageBox.confirm(t('确认取消该评估运行？'), t('提示'), { type: 'warning' });
		const res = await evalService.eval_run.cancel({ evalRunId: row.id });
		if (res?.cancelled === false) {
			ElMessage.warning(t('运行已结束，无需取消'));
		} else {
			ElMessage.success(t('已取消'));
		}
		Crud.value?.refresh();
	} catch (err: any) {
		// 用户点「取消」按钮（ElMessageBox 抛 'cancel'）不算错误
		if (err !== 'cancel' && err?.message !== 'cancel') {
			ElMessage.error(`${t('取消失败')}: ${err?.message || err}`);
		}
	}
}

function goCompare() {
	if (selectedRuns.value.length !== 2) return;
	// 按创建时间升序：A=基线 B=新版，保证 diff 方向稳定（B 相对 A）
	const [baseline, newer] = [...selectedRuns.value].sort(
		(a: any, b: any) => new Date(a.createTime).getTime() - new Date(b.createTime).getTime()
	);
	router.push({
		path: '/workflow/eval/compare',
		query: { runA: baseline.id, runB: newer.id }
	});
}

// 趋势对比：选 ≥2 个 run（按创建时间排序），跳转趋势折线页看多版本演进
function goTrend() {
	if (selectedRuns.value.length < 2) return;
	const ids = [...selectedRuns.value]
		.sort((a: any, b: any) => new Date(a.createTime).getTime() - new Date(b.createTime).getTime())
		.map((r: any) => r.id);
	router.push({ path: '/workflow/eval/trend', query: { runIds: ids.join(',') } });
}

// 详情抽屉
const detail = reactive<{ visible: boolean; runId: number | null; run: any; cases: any[]; total: number; page: number; size: number }>({
	visible: false,
	runId: null,
	run: null,
	cases: [],
	total: 0,
	page: 1,
	size: 20
});
async function openDetail(row: any) {
	detail.runId = row.id;
	detail.run = row; // 先用列表行兜底
	detail.page = 1;
	detail.visible = true;
	await loadCases();
	// 拉取最新完整 run 数据，避免列表快照过时（运行中状态/汇总可能已变化）
	try {
		detail.run = await evalService.eval_run.info({ id: row.id });
	} catch (e) {
		// 拉取失败保留列表行兜底
		console.warn('[workflow_eval/run] 拉取 eval_run.info 失败，保留列表行兜底', e);
	}
}
async function loadCases() {
	if (!detail.runId) return;
	const res = await evalService.eval_run.cases({ evalRunId: detail.runId, page: detail.page, size: detail.size });
	detail.cases = res.list || [];
	detail.total = res.pagination?.total || 0;
}
function onDetailPage(p: number) {
	detail.page = p;
	loadCases();
}

// 标注抽屉：从用例结果行打开，自动绑定 caseResultId + 透传上下文
const annotation = reactive<{ visible: boolean; caseResultId: number; context: any }>({
	visible: false,
	caseResultId: 0,
	context: {}
});
const annotationQueue = ref<any[]>([]);
const annotationInitialIndex = ref(0);
function openAnnotation(row: any) {
	// 当前页用例结果作为队列，启用沉浸式标注
	annotationQueue.value = detail.cases;
	annotationInitialIndex.value = detail.cases.findIndex((r: any) => r.id === row.id);
	if (annotationInitialIndex.value < 0) annotationInitialIndex.value = 0;

	// 兼容原单条模式（抽屉会优先用队列）
	annotation.caseResultId = row.id;
	annotation.context = {
		inputData: row.inputData,
		actualOutput: row.actualOutput,
		expectedOutput: row.expectedOutput,
		score: row.score,
		passed: row.passed,
		evaluatorDetail: row.evaluatorDetail
	};
	annotation.visible = true;
}
</script>

<style scoped>
.detail-summary { margin-bottom: 8px; }
.detail-pager { margin-top: 12px; text-align: right; }
</style>
