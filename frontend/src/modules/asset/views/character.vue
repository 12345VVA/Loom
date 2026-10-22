<script setup lang="ts">
// 角色库管理页（设计 5.2）：封面墙（默认）+ 表格双形态；upsert tabs 分组；
// 状态操作按权限矩阵；published 保存前引用计数确认（验收 13）。
import { computed, markRaw, reactive, ref } from 'vue';
import { useI18n } from 'vue-i18n';
import { ElMessage, ElMessageBox } from 'element-plus';
import { useCool } from '/@/cool';
import { useCrud, useTable, useUpsert } from '@cool-vue/crud';
import { useDict } from '/$/dict';
import DictSelect from '/$/dict/components/dict-select.vue';
import RefImageManager, { type RefImageEntry } from '../components/ref-image-manager.vue';
import { useUserStore } from '/$/base/store/user';

defineOptions({ name: 'asset-character' });

const { service } = useCool();
const { t } = useI18n();
const userStore = useUserStore();
const { dict } = useDict();

const serviceAsset = service.asset.character;
const dictType = 'asset_character_type';
const categoryOptions = computed(() => dict.get(dictType).value ?? []);

interface AssetRow {
	id: number;
	code: string;
	name: string;
	status: string;
	category?: string | null;
	coverUrl?: string | null;
	coverMediaId?: number | null;
	mediaItems?: { id: number; url: string; status: string }[];
	missingMediaIds?: number[];
	createdBy?: number | null;
	createTime?: string;
	appearancePrompt?: string | null;
	negativePrompt?: string | null;
	refImageIds?: string | null;
	tags?: string | null;
	attributes?: string | null;
	voicePrompt?: string | null;
	preferredProfileCode?: string | null;
	preferredSize?: string | null;
}

type AssetUpsertForm = Omit<Partial<AssetRow>, 'refImageIds'> & { refImageIds?: unknown; _mediaItems?: { id: number; url: string }[] };

type AssetPageResult = { list: AssetRow[]; pagination: { page: number; size: number; total: number } };


// ---- 视图形态 ----
const viewMode = ref<'wall' | 'table'>('wall');
const wallList = ref<AssetRow[]>([]);
const wallLoading = ref(false);
const wallPage = reactive({ page: 1, size: 24, total: 0 });

async function refreshWall() {
	wallLoading.value = true;
	try {
		const res = (await serviceAsset.page({ page: wallPage.page, size: wallPage.size })) as unknown as AssetPageResult;
		wallPage.total = res.pagination.total;
		wallList.value = res.list || [];
	} finally {
		wallLoading.value = false;
	}
}

// ---- 状态枚举（代码枚举，组件内常量）----
const statusOptions = [
	{ label: t('草稿'), value: 'draft' },
	{ label: t('已发布'), value: 'published' },
	{ label: t('已归档'), value: 'archived' }
];
const statusColors: Record<string, string> = { draft: 'info', published: 'success', archived: 'warning' };

function isMine(row: AssetRow) {
	return row.createdBy && row.createdBy === userStore.info?.id;
}
const isAdmin = computed(() => !!userStore.info?.isSuperAdmin);

function canEdit(row: AssetRow) {
	if (row.status === 'archived') return false;
	if (isMine(row)) return true;
	return row.status === 'published' && isAdmin.value;
}

// ---- 表格形态 ----
const Table = useTable({
	columns: [
		{ type: 'selection' },
		{ label: t('封面'), prop: 'coverUrl', component: { name: 'cl-image', props: { size: 48 } } },
		{ label: t('标识'), prop: 'code', minWidth: 140 },
		{ label: t('名称'), prop: 'name', minWidth: 120 },
		{ label: t('分类'), prop: 'category', minWidth: 90 },
		{
			label: t('状态'),
			prop: 'status',
			dict: statusOptions.map((o) => ({ ...o, type: statusColors[o.value] })),
			dictColor: true
		},
		{ label: t('创建时间'), prop: 'createTime', minWidth: 160, sortable: 'desc' },
		{
			type: 'op',
			width: 220,
			buttons: ['edit', 'delete', 'slot-op']
		}
	],
	contextMenu: ['refresh']
});

const Crud = useCrud({ service: serviceAsset }, (app) => {
	app.refresh();
	if (viewMode.value === 'wall') refreshWall();
});

function switchView(mode: 'wall' | 'table') {
	viewMode.value = mode;
	if (mode === 'wall') refreshWall();
	else Crud.value?.refresh();
}

// ---- 状态迁移 / fork ----
async function transition(row: AssetRow, action: 'publish' | 'archive' | 'restore') {
	await (serviceAsset as unknown as Record<string, (args: { id: number }) => Promise<unknown>>)[action]({ id: row.id });
	ElMessage.success(t('操作成功'));
	Crud.value?.refresh();
	if (viewMode.value === 'wall') refreshWall();
}

async function fork(row: AssetRow) {
	const res = (await serviceAsset.fork({ id: row.id })) as unknown as { code: string };
	ElMessage.success(t('已复制为草稿：{code}', { code: res.code }));
	Crud.value?.refresh();
	if (viewMode.value === 'wall') refreshWall();
}

// ---- upsert ----
const Upsert = useUpsert({
	dialog: { width: '900px' },
	props: { labelWidth: '110px' },
	items: [
		{
			type: 'tabs',
			props: {
				type: 'card',
				labels: [
					{ label: t('基础信息'), value: 'base' },
					{ label: t('外观 Prompt'), value: 'prompt' },
					{ label: t('参考图集'), value: 'refs' },
					{ label: t('推荐参数'), value: 'params' },
					{ label: t('标签与档案'), value: 'extra' }
				]
			}
		},
		{ label: t('标识'), prop: 'code', group: 'base', required: true, component: { name: 'el-input' } },
		{ label: t('名称'), prop: 'name', group: 'base', required: true, component: { name: 'el-input' } },
		{
			label: t('角色类型'),
			prop: 'category',
			group: 'base',
			component: { vm: markRaw(DictSelect), props: { dictType } }
		},
		{ label: t('封面'), prop: 'coverMediaId', group: 'base', component: { name: 'el-input', props: { placeholder: t('媒体资产 ID') } } },
		{
			label: t('外观正向 Prompt'),
			prop: 'appearancePrompt',
			group: 'prompt',
			component: { name: 'el-input', props: { type: 'textarea', rows: 6, placeholder: t('唯一拼接源，支持双花括号变量占位') } }
		},
		{
			label: t('变量槽'),
			prop: '_varSlots',
			group: 'prompt',
			component: { name: 'slot-varSlots' }
		},
		{
			label: t('角色负面词'),
			prop: 'negativePrompt',
			group: 'prompt',
			component: { name: 'el-input', props: { type: 'textarea', rows: 3 } }
		},
		{
			label: t('参考图集'),
			prop: 'refImageIds',
			group: 'refs',
			component: { name: 'slot-refImages' }
		},
		{
			label: t('推荐 Profile'),
			prop: 'preferredProfileCode',
			group: 'params',
			component: { name: 'el-input', props: { placeholder: t('推荐渠道的 profile code') } }
		},
		{ label: t('推荐尺寸'), prop: 'preferredSize', group: 'params', component: { name: 'el-input' } },
		{ label: t('搜索标签'), prop: 'tags', group: 'extra', component: { name: 'el-input', props: { placeholder: t('JSON 数组，仅用于搜索') } } },
		{ label: t('属性档案'), prop: 'attributes', group: 'extra', component: { name: 'el-input', props: { type: 'textarea', rows: 5, placeholder: t('JSON 结构化属性，不参与拼接') } } },
		{ label: t('对话人设'), prop: 'voicePrompt', group: 'extra', component: { name: 'el-input', props: { type: 'textarea', rows: 3 } } }
	],
	onOpen() {
		// 旧数据/空值初始化（cool-crud-conventions.mdc）：后端 JSON Text 可能是字符串或 null
		const form = Upsert.value?.form as AssetUpsertForm;
		if (!form) return;
		if (typeof form.refImageIds === 'string') {
			try {
				form.refImageIds = JSON.parse(form.refImageIds || '[]');
			} catch {
				form.refImageIds = [];
			}
		}
		if (!Array.isArray(form.refImageIds)) form.refImageIds = [];
	},
	onSubmit(data: AssetUpsertForm, { next }: { next: (payload: AssetUpsertForm) => void }) {
		// 提交转换：entries → JSON 字符串（upload.mdc：结构不一致在提交前显式转换）
		const payload: AssetUpsertForm = { ...data };
		payload.refImageIds = JSON.stringify(
			((data.refImageIds as RefImageEntry[]) || []).map((e: RefImageEntry) => {
				const entry: RefImageEntry = { id: e.id };
				if (e.role) entry.role = e.role;
				return entry;
			})
		);
		payload.tags = data.tags || null;
		payload.attributes = data.attributes || null;
		next(payload);
	},
	onOpened(data: AssetRow) {
		// 参考图元信息回填（info 接口 mediaItems）+ published 编辑确认（验收 13）
		const form = Upsert.value?.form as AssetUpsertForm;
		if (form) form._mediaItems = data?.mediaItems || [];
		if (data?.status === 'published') {
			serviceAsset
				.referenceStats({ id: data.id })
				.then((stats: { successCount?: number; lastProducedAt?: string | null }) => {
					const message =
						(stats.successCount ?? 0) > 0
							? t('该角色累计成功产出 {n} 次，修改将影响后续所有生成', { n: stats.successCount })
							: t('该资产可能被工作流引用，修改将影响后续执行');
					ElMessageBox.confirm(message, t('编辑已发布资产'), { type: 'warning' }).catch(() => {
						Upsert.value?.close();
					});
				})
				.catch(() => undefined);
		}
	}
});

// 变量槽提取（只读预览）
const varSlots = computed(() => {
	const raw = String((Upsert.value?.form as AssetUpsertForm)?.appearancePrompt || '');
	const found: string[] = [];
	const re = /\{\{\s*(\w+)\s*\}\}/g;
	let m: RegExpExecArray | null;
	while ((m = re.exec(raw))) {
		if (!found.includes(m[1])) found.push(m[1]);
	}
	return found;
});

// ---- 详情抽屉 ----
const drawer = reactive({ visible: false, row: null as AssetRow | null });
const detailStats = ref<{ successCount: number; lastProducedAt: string | null } | null>(null);

function openDetail(row: AssetRow) {
	drawer.row = row;
	drawer.visible = true;
	detailStats.value = null;
	serviceAsset
		.referenceStats({ id: row.id })
		.then((s: { successCount?: number; lastProducedAt?: string | null }) => (detailStats.value = { successCount: s.successCount ?? 0, lastProducedAt: s.lastProducedAt ?? null }))
		.catch(() => undefined);
}
</script>

<template>
	<cl-crud ref="Crud">
		<cl-row>
			<cl-refresh-btn />
			<cl-add-btn />
			<cl-multi-delete-btn />
			<el-radio-group :model-value="viewMode" size="small" class="view-switch" @update:model-value="(val) => switchView(val as 'wall' | 'table')">
				<el-radio-button value="wall">{{ $t('封面墙') }}</el-radio-button>
				<el-radio-button value="table">{{ $t('表格') }}</el-radio-button>
			</el-radio-group>
			<cl-flex1 />
			<cl-filter :label="$t('状态')">
				<cl-select :options="statusOptions" prop="status" />
			</cl-filter>
			<cl-filter :label="$t('分类')">
				<cl-select :options="categoryOptions" prop="category" />
			</cl-filter>
			<cl-search-key />
		</cl-row>

		<!-- 封面墙（默认形态） -->
		<cl-row v-if="viewMode === 'wall'">
			<div v-loading="wallLoading" class="wall">
				<div v-for="row in wallList" :key="row.id" class="card" @click="openDetail(row)">
					<el-image :src="row.coverUrl || row.mediaItems?.[0]?.url" fit="cover" class="cover">
						<template #error>
							<div class="cover-empty">{{ $t('无封面') }}</div>
						</template>
					</el-image>
					<div class="info">
						<span class="name">{{ row.name }}</span>
						<el-tag size="small" :type="(statusColors[row.status] as any) || 'info'">
							{{ $t(row.status === 'draft' ? '草稿' : row.status === 'published' ? '已发布' : '已归档') }}
						</el-tag>
					</div>
					<div class="sub">
						<span>{{ row.code }}</span>
						<span v-if="!isMine(row)">{{ $t('他人') }}</span>
					</div>
				</div>
				<el-empty v-if="!wallLoading && !wallList.length" :description="$t('暂无角色')" />
			</div>
		</cl-row>

		<!-- 表格形态 -->
		<cl-row v-else>
			<cl-table ref="Table">
				<template #slot-op="{ scope }">
					<el-button v-if="canEdit(scope.row)" link type="primary" size="small" @click="openDetail(scope.row)">
						{{ $t('详情') }}
					</el-button>
					<el-button
						v-if="scope.row.status === 'draft' && (isMine(scope.row) || isAdmin)"
						v-permission="serviceAsset.permission.publish"
						link
						type="success"
						size="small"
						@click="transition(scope.row, 'publish')"
					>
						{{ $t('发布') }}
					</el-button>
					<el-button
						v-if="scope.row.status === 'published' && (isMine(scope.row) || isAdmin)"
						v-permission="serviceAsset.permission.archive"
						link
						type="warning"
						size="small"
						@click="transition(scope.row, 'archive')"
					>
						{{ $t('归档') }}
					</el-button>
					<el-button
						v-if="scope.row.status === 'archived' && (isMine(scope.row) || isAdmin)"
						v-permission="serviceAsset.permission.restore"
						link
						type="primary"
						size="small"
						@click="transition(scope.row, 'restore')"
					>
						{{ $t('恢复') }}
					</el-button>
					<el-button
						v-if="scope.row.status === 'published'"
						v-permission="serviceAsset.permission.fork"
						link
						type="primary"
						size="small"
						@click="fork(scope.row)"
					>
						{{ $t('复制副本') }}
					</el-button>
				</template>
			</cl-table>
		</cl-row>

		<cl-row>
			<cl-flex1 />
			<el-pagination
				v-if="viewMode === 'wall'"
				v-model:current-page="wallPage.page"
				:page-size="wallPage.size"
				:total="wallPage.total"
				layout="prev, pager, next"
				@current-change="refreshWall"
			/>
			<cl-pagination v-else />
		</cl-row>

		<cl-upsert ref="Upsert">
			<template #slot-varSlots>
				<div class="var-slots">
					<el-tag v-for="name in varSlots" :key="name" size="small" class="slot">{{ name }}</el-tag>
					<span v-if="!varSlots.length" class="none">{{ $t('无变量占位') }}</span>
				</div>
			</template>
			<template #slot-refImages="{ scope }">
				<ref-image-manager
					:model-value="(scope.refImageIds || []).map((e: any) => ({
						id: e.id,
						role: e.role,
						_url: (scope._mediaItems || []).find((m: any) => m.id === e.id)?.url
					}))"
					@update:model-value="(v: any) => (scope.refImageIds = v)"
				/>
			</template>
		</cl-upsert>

		<!-- 详情抽屉 -->
		<el-drawer v-model="drawer.visible" :title="drawer.row?.name || ''" size="480px">
			<template v-if="drawer.row">
				<el-descriptions :column="1" border size="small">
					<el-descriptions-item :label="$t('标识')">{{ drawer.row.code }}</el-descriptions-item>
					<el-descriptions-item :label="$t('状态')">{{ drawer.row.status }}</el-descriptions-item>
					<el-descriptions-item :label="$t('成功产出')">
						{{ detailStats?.successCount ?? $t('加载中') }}
					</el-descriptions-item>
				</el-descriptions>
				<div class="detail-refs">
					<div class="head">{{ $t('参考图') }}</div>
					<el-image
						v-for="m in drawer.row.mediaItems || []"
						:key="m.id"
						:src="m.url"
						:preview-src-list="[m.url]"
						fit="cover"
						class="ref"
					/>
					<span v-for="mid in drawer.row.missingMediaIds || []" :key="mid" class="missing">
						{{ $t('#{id} 已失效', { id: mid }) }}
					</span>
				</div>
				<div class="detail-prompt">
					<div class="head">{{ $t('外观 Prompt') }}</div>
					<pre>{{ drawer.row.appearancePrompt || '—' }}</pre>
				</div>
			</template>
		</el-drawer>
	</cl-crud>
</template>

<style scoped>
.view-switch {
	margin-left: 12px;
}
.wall {
	display: grid;
	grid-template-columns: repeat(auto-fill, minmax(160px, 1fr));
	gap: 14px;
	width: 100%;
	padding: 4px;
	min-height: 200px;
}
.card {
	border: 1px solid var(--el-border-color-lighter);
	border-radius: 8px;
	overflow: hidden;
	cursor: pointer;
	transition: box-shadow 0.2s;
}
.card:hover {
	box-shadow: var(--el-box-shadow-light);
}
.cover {
	width: 100%;
	height: 130px;
	display: block;
}
.cover-empty {
	height: 130px;
	display: flex;
	align-items: center;
	justify-content: center;
	color: var(--el-text-color-secondary);
	background: var(--el-fill-color-light);
}
.info {
	display: flex;
	align-items: center;
	justify-content: space-between;
	padding: 8px 10px 2px;
}
.name {
	font-weight: 500;
	overflow: hidden;
	text-overflow: ellipsis;
	white-space: nowrap;
}
.sub {
	display: flex;
	justify-content: space-between;
	padding: 0 10px 8px;
	font-size: 12px;
	color: var(--el-text-color-secondary);
}
.var-slots {
	display: flex;
	gap: 6px;
	flex-wrap: wrap;
}
.var-slots .none {
	color: var(--el-text-color-secondary);
	font-size: 12px;
}
.detail-refs,
.detail-prompt {
	margin-top: 14px;
}
.head {
	font-size: 12px;
	color: var(--el-text-color-secondary);
	margin-bottom: 6px;
}
.detail-refs .ref {
	width: 80px;
	height: 80px;
	border-radius: 6px;
	margin-right: 8px;
}
.missing {
	color: var(--el-color-danger);
	font-size: 12px;
	margin-right: 8px;
}
.detail-prompt pre {
	margin: 0;
	padding: 8px;
	background: var(--el-fill-color-light);
	border-radius: 6px;
	white-space: pre-wrap;
	word-break: break-all;
	font-size: 12px;
}
</style>
