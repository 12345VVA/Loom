<template>
	<div class="ai-dashboard" v-loading="loading">
		<header class="toolbar">
			<cl-select v-model="query.groupBy" :options="groupOptions" :width="160" />
			<el-input-number v-model="query.days" :min="1" :max="365" controls-position="right" />
			<el-button type="primary" :loading="loading" @click="loadStats">{{ $t('刷新') }}</el-button>
		</header>

		<section class="summary">
			<div class="summary-item">
				<span>{{ $t('调用') }}</span>
				<strong>{{ stats.total }}</strong>
			</div>
			<div class="summary-item">
				<span>{{ $t('成功率') }}</span>
				<strong>{{ (stats.successRate * 100).toFixed(2) }}%</strong>
			</div>
			<div class="summary-item">
				<span>Tokens</span>
				<strong>{{ stats.totalTokens }}</strong>
			</div>
			<div class="summary-item">
				<span>Cost USD</span>
				<strong>{{ stats.costUsd }}</strong>
			</div>
			<div class="summary-item">
				<span>{{ $t('平均延迟') }}</span>
				<strong>{{ stats.avgLatencyMs }}ms</strong>
			</div>
		</section>

		<el-table :data="stats.groups" border height="100%">
			<el-table-column prop="key" :label="$t('分组')" min-width="160" />
			<el-table-column prop="total" :label="$t('调用')" width="100" />
			<el-table-column prop="success" :label="$t('成功')" width="100" />
			<el-table-column prop="error" :label="$t('错误')" width="100" />
			<el-table-column prop="totalTokens" label="Tokens" min-width="120" />
			<el-table-column prop="costUsd" label="Cost USD" min-width="120" />
			<el-table-column prop="avgLatencyMs" :label="$t('平均延迟(ms)')" min-width="140" />
		</el-table>
	</div>
</template>

<script lang="ts" setup>
defineOptions({
	name: 'ai-dashboard'
});

import { onMounted, reactive, ref } from 'vue';
import { ElMessage } from 'element-plus';
import { useCool } from '/@/cool';
import { useI18n } from 'vue-i18n';

const { service } = useCool();
const { t } = useI18n();

const groupOptions = [
	{ label: t('日期'), value: 'day' },
	{ label: t('用户'), value: 'user' },
	{ label: 'Profile', value: 'profile' },
	{ label: t('模型'), value: 'model' }
];
const query = reactive({
	days: 14,
	groupBy: 'day'
});
const stats = reactive({
	total: 0,
	success: 0,
	error: 0,
	successRate: 0,
	avgLatencyMs: 0,
	totalTokens: 0,
	costUsd: 0,
	groups: [] as any[]
});

const loading = ref(false);

onMounted(loadStats);

async function loadStats() {
	loading.value = true;
	try {
		const res = await (service.ai as any).dashboard.cost({
			days: query.days,
			groupBy: query.groupBy
		});
		Object.assign(stats, {
			total: res?.total || 0,
			success: res?.success || 0,
			error: res?.error || 0,
			successRate: res?.successRate || 0,
			avgLatencyMs: res?.avgLatencyMs || 0,
			totalTokens: res?.totalTokens || 0,
			costUsd: res?.costUsd || 0,
			groups: res?.groups || []
		});
	} catch (err: any) {
		ElMessage.error(err?.message || t('加载统计数据失败'));
	} finally {
		loading.value = false;
	}
}
</script>

<style lang="scss" scoped>
.ai-dashboard {
	display: grid;
	grid-template-rows: auto auto minmax(0, 1fr);
	gap: 12px;
	height: 100%;
	min-height: 640px;
}

.toolbar {
	display: flex;
	gap: 10px;
	align-items: center;
}

.summary {
	display: grid;
	grid-template-columns: repeat(auto-fit, minmax(160px, 1fr));
	gap: 10px;
}

.summary-item {
	display: grid;
	gap: 6px;
	padding: 12px;
	border: 1px solid var(--el-border-color-light);
	border-radius: 6px;
	background: var(--el-bg-color);

	span {
		color: var(--el-text-color-secondary);
		font-size: 13px;
	}

	strong {
		font-size: 22px;
		font-weight: 700;
	}
}
</style>
