<template>
	<div class="compare-page" v-loading="loading">
		<div class="compare-header">
			<el-button @click="$router.back()">{{ $t('返回') }}</el-button>
			<h3 style="margin: 0">{{ $t('回归对比') }}</h3>
		</div>

		<el-alert
			v-if="data.verdict"
			:type="verdictType(data.verdict)"
			:title="verdictLabel(data.verdict)"
			:closable="false"
			show-icon
			style="margin-bottom: 12px"
		/>

		<el-card v-if="data" class="compare-card">
			<div class="compare-row">
				<div class="run-box">
					<h4>{{ data.runA.versionLabel || `#${data.runA.id}` }} (A)</h4>
					<div>{{ $t('通过率') }} {{ ((data.runA.metrics?.passRate ?? 0) * 100).toFixed(1) }}%</div>
					<div>{{ $t('平均分') }} {{ (data.runA.metrics?.avgScore ?? 0).toFixed(3) }}</div>
					<div>P95 {{ data.runA.metrics?.p95LatencyMs ?? 0 }}ms</div>
				</div>
				<div class="diff-box">
					<div>{{ $t('通过率差') }} <b>{{ ((data.metricsDiff?.passRate ?? 0) * 100).toFixed(1) }}%</b></div>
					<div>{{ $t('平均分差') }} <b>{{ (data.metricsDiff?.avgScore ?? 0).toFixed(3) }}</b></div>
					<div>P95 {{ $t('差') }} <b>{{ data.metricsDiff?.p95LatencyMs ?? 0 }}ms</b></div>
					<div v-if="data.scoreDiff" style="margin-top: 6px">
						{{ $t('score 差') }} <b>{{ (data.scoreDiff.delta ?? 0).toFixed(3) }}</b>
						<span
							v-if="data.scoreDiff.ciLow !== null && data.scoreDiff.ciLow !== undefined"
							style="color: #999; font-size: 12px"
						>[{{ data.scoreDiff.ciLow.toFixed(3) }}, {{ data.scoreDiff.ciHigh.toFixed(3) }}]</span>
						<el-tag v-if="data.scoreDiff.significant" type="danger" size="small" style="margin-left: 4px">{{ $t('显著') }}</el-tag>
					</div>
				</div>
				<div class="run-box">
					<h4>{{ data.runB.versionLabel || `#${data.runB.id}` }} (B)</h4>
					<div>{{ $t('通过率') }} {{ ((data.runB.metrics?.passRate ?? 0) * 100).toFixed(1) }}%</div>
					<div>{{ $t('平均分') }} {{ (data.runB.metrics?.avgScore ?? 0).toFixed(3) }}</div>
					<div>P95 {{ data.runB.metrics?.p95LatencyMs ?? 0 }}ms</div>
				</div>
			</div>
		</el-card>

		<el-tabs v-if="data" class="compare-tabs">
			<el-tab-pane :label="$t('退化') + `(${data.regressed.length})`">
				<el-table :data="data.regressed" border>
					<el-table-column prop="caseKey" :label="$t('用例')" min-width="140" />
					<el-table-column prop="scoreA" :label="$t('A 分')" width="100" />
					<el-table-column prop="scoreB" :label="$t('B 分')" width="100" />
					<el-table-column prop="delta" :label="$t('变化')" width="100" />
				</el-table>
			</el-tab-pane>
			<el-tab-pane :label="$t('改善') + `(${data.improved.length})`">
				<el-table :data="data.improved" border>
					<el-table-column prop="caseKey" :label="$t('用例')" min-width="140" />
					<el-table-column prop="scoreA" :label="$t('A 分')" width="100" />
					<el-table-column prop="scoreB" :label="$t('B 分')" width="100" />
					<el-table-column prop="delta" :label="$t('变化')" width="100" />
				</el-table>
			</el-tab-pane>
			<el-tab-pane :label="$t('仅A') + `(${data.onlyA.length})`">
				<el-table :data="data.onlyA.map((k: string) => ({ caseKey: k }))" border>
					<el-table-column prop="caseKey" :label="$t('用例')" />
				</el-table>
			</el-tab-pane>
			<el-tab-pane :label="$t('仅B') + `(${data.onlyB.length})`">
				<el-table :data="data.onlyB.map((k: string) => ({ caseKey: k }))" border>
					<el-table-column prop="caseKey" :label="$t('用例')" />
				</el-table>
			</el-tab-pane>
		</el-tabs>

		<el-empty v-if="!data && !loading" :description="$t('请从评估运行列表选择两个运行进行对比')" />
	</div>
</template>

<script lang="ts" setup>
defineOptions({ name: 'workflow-eval-compare' });

import { onMounted, ref } from 'vue';
import { useRoute } from 'vue-router';
import { ElMessage } from 'element-plus';
import { useCool } from '/@/cool';
import { useI18n } from 'vue-i18n';
import { verdictType } from '../utils/format';

const route = useRoute();
const { service } = useCool();
const { t } = useI18n();
const evalService = (service as any).workflow_eval;

const data = ref<any>(null);
const loading = ref(false);

// verdict 整体判定文案与样式（B 相对 A：显著退化/显著改善/无显著变化/样本不足）
function verdictLabel(v: string) {
	return {
		regression: t('显著退化（B 比 A 明显变差）'),
		improvement: t('显著改善（B 比 A 明显变好）'),
		insignificant: t('无显著变化（差异在统计噪声范围内）'),
		insufficient_sample: t('样本量不足，无法判定显著性')
	}[v] || v;
}

onMounted(async () => {
	const runA = Number(route.query.runA);
	const runB = Number(route.query.runB);
	if (!runA || !runB) {
		ElMessage.warning(t('请从评估运行列表选择两个运行进行对比'));
		return;
	}
	loading.value = true;
	try {
		data.value = await evalService.eval_run.compare({ runA, runB });
	} catch (err: any) {
		ElMessage.error(err.message || err);
	} finally {
		loading.value = false;
	}
});
</script>

<style scoped>
.compare-page { padding: 12px; }
.compare-header { display: flex; align-items: center; gap: 16px; margin-bottom: 12px; }
.compare-row { display: grid; grid-template-columns: 1fr 1fr 1fr; gap: 16px; align-items: center; }
.run-box h4 { margin: 0 0 8px; }
.diff-box { text-align: center; }
.compare-tabs { margin-top: 16px; }
</style>
