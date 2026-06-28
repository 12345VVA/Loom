<template>
	<div class="trend-page" v-loading="loading">
		<div class="trend-header">
			<el-button @click="$router.back()">{{ $t('返回') }}</el-button>
			<h3 style="margin: 0">{{ $t('趋势对比') }}</h3>
			<cl-flex1 />
			<el-select v-model="metric" style="width: 170px">
				<el-option :label="$t('通过率')" value="passRate" />
				<el-option :label="$t('平均分')" value="avgScore" />
				<el-option :label="$t('P95 延迟(ms)')" value="p95LatencyMs" />
				<el-option :label="$t('用例总数')" value="total" />
				<el-option :label="$t('Token 总量')" value="totalTokens" />
			</el-select>
		</div>

		<el-card v-if="runs.length">
			<v-chart :option="chartOption" autoresize style="height: 420px" />
		</el-card>

		<el-card v-if="runs.length" style="margin-top: 12px">
			<el-table :data="runs" border size="small">
				<el-table-column prop="versionLabel" :label="$t('版本号')" min-width="120" />
				<el-table-column prop="createTime" :label="$t('创建时间')" min-width="160" />
				<el-table-column prop="passRate" :label="$t('通过率')" width="100">
					<template #default="{ row }">{{ ((row.passRate ?? 0) * 100).toFixed(1) }}%</template>
				</el-table-column>
				<el-table-column prop="avgScore" :label="$t('平均分')" width="100">
					<template #default="{ row }">{{ (row.avgScore ?? 0).toFixed(3) }}</template>
				</el-table-column>
				<el-table-column prop="p95LatencyMs" :label="$t('P95(ms)')" width="100" />
				<el-table-column prop="total" :label="$t('总数')" width="80" />
			</el-table>
		</el-card>

		<el-empty v-if="!runs.length && !loading" :description="$t('请从评估运行列表选择至少两个运行查看趋势')" />
	</div>
</template>

<script lang="ts" setup>
defineOptions({ name: 'workflow-eval-trend' });

import { computed, onMounted, ref } from 'vue';
import { useRoute } from 'vue-router';
import { ElMessage } from 'element-plus';
import { useCool } from '/@/cool';
import { useI18n } from 'vue-i18n';

const route = useRoute();
const { service } = useCool();
const { t } = useI18n();
const evalService = (service as any).workflow_eval;

const runs = ref<any[]>([]);
const loading = ref(false);
const metric = ref('passRate');

onMounted(async () => {
	const ids = String(route.query.runIds || '')
		.split(',')
		.map(s => Number(s))
		.filter(n => !Number.isNaN(n) && n > 0);
	if (ids.length < 2) {
		ElMessage.warning(t('请从评估运行列表选择至少两个运行'));
		return;
	}
	loading.value = true;
	try {
		const results = await Promise.all(
			ids.map(id => evalService.eval_run.info({ id }).catch(() => null))
		);
		runs.value = results
			.filter(Boolean)
			.sort((a: any, b: any) => new Date(a.createTime).getTime() - new Date(b.createTime).getTime());
	} finally {
		loading.value = false;
	}
});

// 趋势折线：x = 版本/run，y = 选中指标；随 metric 切换
const chartOption = computed(() => ({
	tooltip: { trigger: 'axis' },
	xAxis: {
		type: 'category',
		data: runs.value.map(r => r.versionLabel || `#${r.id}`)
	},
	yAxis: { type: 'value' },
	series: [
		{
			type: 'line',
			data: runs.value.map(r => Number(r[metric.value] ?? 0)),
			smooth: true,
			label: { show: true },
			areaStyle: { opacity: 0.1 }
		}
	],
	grid: { left: 50, right: 30, top: 30, bottom: 40 }
}));
</script>

<style scoped>
.trend-page { padding: 12px; }
.trend-header { display: flex; align-items: center; gap: 16px; margin-bottom: 12px; }
</style>
