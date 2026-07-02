<template>
	<div class="version-page" v-loading="loading">
		<div class="version-header">
			<el-button @click="$router.back()">{{ $t('返回') }}</el-button>
			<h3 style="margin: 0">
				{{ $t('版本历史') }}
				<span v-if="defName" style="color: #999; font-weight: normal; margin-left: 8px">— {{ defName }}</span>
			</h3>
			<cl-flex1 />
			<el-button
				type="primary"
				:disabled="selected.length !== 2"
				@click="loadDiff"
			>{{ $t('对比选中版本(选2个)') }}</el-button>
		</div>

		<el-table :data="versions" border @selection-change="(r: any[]) => (selected = r)">
			<el-table-column type="selection" width="45" />
			<el-table-column prop="versionNo" :label="$t('版本号')" width="120">
				<template #default="{ row }"><b>{{ formatVersionNo(row.versionNo) }}</b></template>
			</el-table-column>
			<el-table-column prop="status" :label="$t('状态')" width="110">
				<template #default="{ row }">
					<el-tag :type="statusType(row.status)" size="small">{{ statusLabel(row.status) }}</el-tag>
				</template>
			</el-table-column>
			<el-table-column prop="changeNote" :label="$t('变更说明')" min-width="180" show-overflow-tooltip />
			<el-table-column prop="publishedAt" :label="$t('发布时间')" width="170" />
			<el-table-column :label="$t('操作')" width="200">
				<template #default="{ row }">
					<el-button text type="primary" @click="preview(row)">{{ $t('预览') }}</el-button>
					<el-button
						text
						type="warning"
						:disabled="row.status === 'draft'"
						@click="rollback(row)"
					>{{ $t('回滚到此') }}</el-button>
				</template>
			</el-table-column>
		</el-table>
		<div class="version-pager">
			<el-pagination
				background
				layout="prev, pager, next"
				:total="total"
				:page-size="size"
				:current-page="page"
				@current-change="onPageChange"
			/>
		</div>

		<!-- diff 结果 -->
		<el-card v-if="diff" class="diff-card">
			<template #header>
				{{ $t('版本对比') }}：{{ formatVersionNo(diff.versionA.versionNo) }} → {{ formatVersionNo(diff.versionB.versionNo) }}
			</template>
			<el-tabs>
				<el-tab-pane :label="$t('新增节点') + `(${diff.nodesAdded.length})`">
					<el-table :data="diff.nodesAdded" border size="small">
						<el-table-column prop="id" :label="$t('节点ID')" />
						<el-table-column prop="type" :label="$t('类型')" />
						<el-table-column prop="name" :label="$t('名称')" />
					</el-table>
				</el-tab-pane>
				<el-tab-pane :label="$t('删除节点') + `(${diff.nodesRemoved.length})`">
					<el-table :data="diff.nodesRemoved" border size="small">
						<el-table-column prop="id" :label="$t('节点ID')" />
						<el-table-column prop="type" :label="$t('类型')" />
					</el-table>
				</el-tab-pane>
				<el-tab-pane :label="$t('修改节点') + `(${diff.nodesModified.length})`">
					<el-table :data="diff.nodesModified" border size="small">
						<el-table-column prop="id" :label="$t('节点ID')" />
						<el-table-column prop="type" :label="$t('类型')" />
					</el-table>
				</el-tab-pane>
				<el-tab-pane :label="$t('连线变化') + `(${diff.edgesAdded.length + diff.edgesRemoved.length})`">
					<h5 v-if="diff.edgesAdded.length">{{ $t('新增') }}</h5>
					<el-table :data="diff.edgesAdded" border size="small">
						<el-table-column prop="source" :label="$t('源')" />
						<el-table-column prop="target" :label="$t('目标')" />
						<el-table-column prop="type" :label="$t('类型')" />
					</el-table>
					<h5 v-if="diff.edgesRemoved.length" style="margin-top: 12px">{{ $t('删除') }}</h5>
					<el-table :data="diff.edgesRemoved" border size="small">
						<el-table-column prop="source" :label="$t('源')" />
						<el-table-column prop="target" :label="$t('目标')" />
						<el-table-column prop="type" :label="$t('类型')" />
					</el-table>
				</el-tab-pane>
			</el-tabs>
		</el-card>

		<!-- 预览抽屉 -->
		<el-drawer v-model="previewVisible" :title="`${formatVersionNo(previewRow?.versionNo)} ${$t('拓扑预览')}`" size="680px">
			<div v-if="previewGraph">
				<h4>{{ $t('节点') }}（{{ previewGraph.nodes?.length || 0 }}）</h4>
				<el-table :data="previewGraph.nodes" border size="small">
					<el-table-column prop="id" :label="$t('ID')" />
					<el-table-column prop="type" :label="$t('类型')" />
					<el-table-column prop="name" :label="$t('名称')" />
				</el-table>
				<h4 style="margin-top: 16px">{{ $t('连线') }}（{{ previewGraph.edges?.length || 0 }}）</h4>
				<el-table :data="previewGraph.edges" border size="small">
					<el-table-column prop="source" :label="$t('源')" />
					<el-table-column prop="target" :label="$t('目标')" />
					<el-table-column prop="type" :label="$t('类型')" />
				</el-table>
			</div>
		</el-drawer>
	</div>
</template>

<script lang="ts" setup>
defineOptions({ name: 'workflow-version' });

import { onMounted, onActivated, ref } from 'vue';
import { useRoute } from 'vue-router';
import { ElMessage, ElMessageBox } from 'element-plus';
import { useCool } from '/@/cool';
import { useI18n } from 'vue-i18n';
import { formatVersionNo } from '../utils';

const route = useRoute();
const { service } = useCool();
const { t } = useI18n();
const wfService = (service as any).workflow;

// 当前页面展示的工作流定义 id（keep-alive 缓存复用：切换不同工作流时需重载）
let activeDefinitionId = Number(route.query.definitionId);
const defName = ref('');
const loading = ref(false);
const versions = ref<any[]>([]);
const total = ref(0);
const page = ref(1);
const size = ref(20);
const selected = ref<any[]>([]);
const diff = ref<any>(null);

// 预览
const previewVisible = ref(false);
const previewRow = ref<any>(null);
const previewGraph = ref<any>(null);

async function initPage(defId: number) {
	if (!defId) {
		ElMessage.warning(t('缺少工作流定义参数'));
		return;
	}
	// 取 definition 名称用于标题
	try {
		const def = await wfService.definition.info({ id: defId });
		defName.value = def.name;
	} catch (e) {
		// ignore
		console.warn('[workflow/version] 拉取 definition.info 用于标题失败', e);
	}
	page.value = 1;
	await loadVersions();
}

onMounted(() => initPage(activeDefinitionId));

// keep-alive 缓存复用：切回本页时若路由指向不同工作流，重置状态并重新加载，
// 避免残留上一个工作流的版本列表/diff/预览（与 editor 画布缓存同源问题）
onActivated(async () => {
	const incoming = Number(route.query.definitionId);
	if (incoming === activeDefinitionId) return;
	activeDefinitionId = incoming;
	selected.value = [];
	diff.value = null;
	previewVisible.value = false;
	await initPage(incoming);
});

async function loadVersions() {
	loading.value = true;
	try {
		const res = await wfService.version.page({ definitionId: activeDefinitionId, page: page.value, size: size.value });
		versions.value = res.list || [];
		total.value = res.pagination?.total || 0;
	} catch (err: any) {
		ElMessage.error(err.message || err);
	} finally {
		loading.value = false;
	}
}

function onPageChange(p: number) {
	page.value = p;
	loadVersions();
}

async function loadDiff() {
	if (selected.value.length !== 2) return;
	// 按版本号升序：A=旧 B=新，保证 diff 方向稳定
	const [a, b] = [...selected.value].sort((x, y) => x.versionNo - y.versionNo);
	try {
		diff.value = await wfService.version.diff({ versionA: a.id, versionB: b.id });
	} catch (err: any) {
		ElMessage.error(err.message || err);
	}
}

async function preview(row: any) {
	previewRow.value = row;
	previewGraph.value = null;
	previewVisible.value = true;
	try {
		const v = await wfService.version.info({ id: row.id });
		previewGraph.value = v.graphJson ? JSON.parse(v.graphJson) : { nodes: [], edges: [] };
	} catch (err: any) {
		ElMessage.error(err.message || err);
	}
}

async function rollback(row: any) {
	try {
		await ElMessageBox.confirm(
			t('将基于 ' + formatVersionNo(row.versionNo) + ' 生成新草稿（线上版本不变），需在编辑器确认后发布。立即上线请勾选。'),
			t('回滚确认'),
			{ type: 'warning', distinguishCancelAndClose: true }
		);
		await wfService.version.rollback({ definitionId: activeDefinitionId, targetVersionId: row.id, immediate: false });
		ElMessage.success(t('已生成回滚草稿，请进入编辑器确认后发布'));
		await loadVersions();
	} catch (e: any) {
		if (e !== 'cancel') ElMessage.error(t('回滚失败：') + (e?.message || e));
	}
}

function statusLabel(s: string) {
	return { draft: t('草稿'), published: t('已发布'), archived: t('已归档') }[s] || s;
}
function statusType(s: string): any {
	return { draft: 'info', published: 'success', archived: '' }[s] || '';
}
</script>

<style scoped>
.version-page { padding: 12px; }
.version-header { display: flex; align-items: center; gap: 16px; margin-bottom: 12px; }
.version-pager { margin-top: 12px; text-align: right; }
.diff-card { margin-top: 16px; }
</style>
