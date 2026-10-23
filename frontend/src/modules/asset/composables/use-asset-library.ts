// 三库页面（角色/场景/风格）共享逻辑：封面墙+表格双形态、状态枚举、行级权限口径、
// 状态迁移/fork、详情抽屉与引用计数、upsert 钩子辅助。视图只保留差异项（service、dictType、文案）。
import { computed, reactive, ref } from 'vue';
import { useI18n } from 'vue-i18n';
import { ElMessage, ElMessageBox } from 'element-plus';
import { useClipboard } from '@vueuse/core';
import { useUserStore } from '/$/base/store/user';
import type { RefImageEntry } from '../components/ref-image-manager.vue';

// 视图行模型：对齐后端 Read 出口 camelCase 字段（场景/风格不含角色专属段，统一可选兼容）
export interface AssetRow {
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

export type AssetUpsertForm = Omit<Partial<AssetRow>, 'refImageIds'> & {
	refImageIds?: unknown;
	_mediaItems?: { id: number; url: string }[];
};

// 三库 service 的公共面（EPS 已为各端点生成具名 Response，三库结构一致）
interface AssetLibService {
	page(data: { page: number; size: number }): Promise<{
		list: unknown[];
		pagination: { page: number; size: number; total: number };
	}>;
	fork(data: { id: number }): Promise<{ code: string }>;
	publish(data: { id: number }): Promise<unknown>;
	archive(data: { id: number }): Promise<unknown>;
	restore(data: { id: number }): Promise<unknown>;
	referenceStats(data: { id: number }): Promise<{
		successCount?: number;
		lastProducedAt?: string | null;
	}>;
}

export type AssetTransitionAction = 'publish' | 'archive' | 'restore';

export function useAssetLibrary(service: AssetLibService, options: { onChanged?: () => void } = {}) {
	const { t } = useI18n();
	const userStore = useUserStore();

	// ---- 状态枚举（代码枚举，模块级共享）----
	const statusOptions = [
		{ label: t('草稿'), value: 'draft' },
		{ label: t('已发布'), value: 'published' },
		{ label: t('已归档'), value: 'archived' }
	];
	const statusColors: Record<string, 'info' | 'success' | 'warning'> = {
		draft: 'info',
		published: 'success',
		archived: 'warning'
	};

	// ---- 行级权限（口径对齐后端 _check_edit_permission：archived 锁死；
	// draft 仅创建者；published 创建者+管理员；删除=创建者或管理员）----
	function isMine(row: AssetRow) {
		return !!row.createdBy && row.createdBy === userStore.info?.id;
	}
	const isAdmin = computed(() => !!userStore.info?.isSuperAdmin);

	function canEdit(row: AssetRow) {
		if (row.status === 'archived') return false;
		if (isMine(row)) return true;
		return row.status === 'published' && isAdmin.value;
	}

	function canDelete(row: AssetRow) {
		return isMine(row) || isAdmin.value;
	}

	// ---- 封面墙 / 表格双形态 ----
	const viewMode = ref<'wall' | 'table'>('wall');
	const wallList = ref<AssetRow[]>([]);
	const wallLoading = ref(false);
	const wallPage = reactive({ page: 1, size: 24, total: 0 });

	async function refreshWall() {
		wallLoading.value = true;
		try {
			const res = await service.page({ page: wallPage.page, size: wallPage.size });
			wallPage.total = res.pagination.total;
			// EPS 实体为全可选宽松形态，收敛为视图行模型（无 id 的残缺行直接丢弃）
			wallList.value = (res.list || []).filter(
				(row): row is AssetRow => !!row && typeof row === 'object' && typeof (row as { id?: unknown }).id === 'number'
			);
		} finally {
			wallLoading.value = false;
		}
	}

	function switchView(mode: 'wall' | 'table') {
		viewMode.value = mode;
		if (mode === 'wall') refreshWall();
		else options.onChanged?.();
	}

	// ---- 状态迁移 / fork ----
	const transitionApi: Record<AssetTransitionAction, (data: { id: number }) => Promise<unknown>> = {
		publish: (data) => service.publish(data),
		archive: (data) => service.archive(data),
		restore: (data) => service.restore(data)
	};

	async function transition(row: AssetRow, action: AssetTransitionAction) {
		if (row.id == null) return;
		await transitionApi[action]({ id: row.id });
		ElMessage.success(t('操作成功'));
		options.onChanged?.();
		if (viewMode.value === 'wall') refreshWall();
	}

	async function fork(row: AssetRow) {
		if (row.id == null) return;
		const res = await service.fork({ id: row.id });
		ElMessage.success(t('已复制为草稿：{code}', { code: res.code }));
		options.onChanged?.();
		if (viewMode.value === 'wall') refreshWall();
	}

	// ---- 详情抽屉（引用计数带竞态保护：慢响应不覆盖后打开的卡）----
	const drawer = reactive({ visible: false, row: null as AssetRow | null });
	const detailStats = ref<{ successCount: number; lastProducedAt: string | null } | null>(null);
	let statsSeq = 0;

	function openDetail(row: AssetRow) {
		drawer.row = row;
		drawer.visible = true;
		detailStats.value = null;
		if (row.id == null) return;
		const seq = ++statsSeq;
		service
			.referenceStats({ id: row.id })
			.then((s) => {
				if (seq !== statsSeq) return;
				detailStats.value = { successCount: s.successCount ?? 0, lastProducedAt: s.lastProducedAt ?? null };
			})
			.catch(() => undefined);
	}

	// ---- 详情抽屉辅助 ----
	const { copy } = useClipboard();

	async function copyDetailPrompt() {
		// 需求 4.4：详情抽屉 prompt 全文一键复制
		const text = drawer.row?.appearancePrompt;
		if (!text) return;
		await copy(text);
		ElMessage.success(t('已复制'));
	}

	function primaryRefId(row: AssetRow | null): number | null {
		// 需求 4.4：详情抽屉 role 标记——refImageIds 首项即 primary（兼容纯 id 旧数组）
		if (!row?.refImageIds) return null;
		try {
			const first = JSON.parse(row.refImageIds)[0];
			if (first == null) return null;
			return typeof first === 'object' ? (first.id ?? null) : first;
		} catch {
			return null;
		}
	}

	// ---- upsert onOpened：参考图元信息回填（info 接口 mediaItems）+ published 编辑确认（验收 13）----
	function onUpsertOpened(data: AssetRow | undefined, form: AssetUpsertForm | undefined, close: () => void) {
		if (form) form._mediaItems = data?.mediaItems || [];
		if (data?.status === 'published' && data.id != null) {
			service
				.referenceStats({ id: data.id })
				.then((stats) => {
					const message =
						(stats.successCount ?? 0) > 0
							? t('该资产累计成功产出 {n} 次，修改将影响后续所有生成', { n: stats.successCount })
							: t('该资产可能被工作流引用，修改将影响后续执行');
					ElMessageBox.confirm(message, t('编辑已发布资产'), { type: 'warning' }).catch(() => {
						close();
					});
				})
				.catch(() => undefined);
		}
	}

	return {
		statusOptions,
		statusColors,
		isMine,
		isAdmin,
		canEdit,
		canDelete,
		viewMode,
		wallList,
		wallLoading,
		wallPage,
		refreshWall,
		switchView,
		transition,
		fork,
		drawer,
		detailStats,
		openDetail,
		copyDetailPrompt,
		primaryRefId,
		onUpsertOpened
	};
}

/** upsert onOpen：后端 JSON Text 可能是字符串或 null（cool-crud-conventions.mdc） */
export function initRefImageForm(form: AssetUpsertForm | undefined) {
	if (!form) return;
	if (typeof form.refImageIds === 'string') {
		try {
			form.refImageIds = JSON.parse(form.refImageIds || '[]');
		} catch {
			form.refImageIds = [];
		}
	}
	if (!Array.isArray(form.refImageIds)) form.refImageIds = [];
}

/** upsert onSubmit：entries → JSON 字符串（upload.mdc：结构不一致在提交前显式转换） */
export function buildSubmitPayload(data: AssetUpsertForm): AssetUpsertForm {
	const payload: AssetUpsertForm = { ...data };
	payload.refImageIds = JSON.stringify(
		((data.refImageIds as RefImageEntry[]) || []).map((e) => {
			const entry: RefImageEntry = { id: e.id };
			if (e.role) entry.role = e.role;
			return entry;
		})
	);
	payload.tags = data.tags || null;
	return payload;
}

/** upsert slot 取值：表单 refImageIds（onOpen 已展开为数组）→ 组件条目（回填媒体缩略图） */
export function refImageModel(form: AssetUpsertForm | undefined): RefImageEntry[] {
	return ((form?.refImageIds as RefImageEntry[]) || []).map((e) => ({
		id: e.id,
		role: e.role,
		_url: (form?._mediaItems || []).find((m) => m.id === e.id)?.url
	}));
}

/** upsert slot 赋值：组件条目 → 表单 refImageIds */
export function refImageChange(form: AssetUpsertForm | undefined, v: RefImageEntry[]) {
	if (form) form.refImageIds = v;
}
