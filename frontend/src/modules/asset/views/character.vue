<script setup lang="ts">
// 角色库管理页（设计 5.2）：封面墙（默认）+ 表格双形态；共享逻辑在 use-asset-library，
// 本页只保留角色差异项（dictType、变量槽预览、attributes/voicePrompt 表单项）。
import { computed, markRaw } from 'vue';
import { useI18n } from 'vue-i18n';
import { useCool } from '/@/cool';
import { useCrud, useTable, useUpsert } from '@cool-vue/crud';
import { useDict } from '/$/dict';
import DictSelect from '/$/dict/components/dict-select.vue';
import RefImageManager from '../components/ref-image-manager.vue';
import AssetCardWall from '../components/asset-card-wall.vue';
import {
	buildSubmitPayload,
	initRefImageForm,
	refImageChange,
	refImageModel,
	useAssetLibrary,
	type AssetRow,
	type AssetUpsertForm
} from '../composables/use-asset-library';

defineOptions({ name: 'asset-character' });

const { service } = useCool();
const { t } = useI18n();
const { dict } = useDict();

const serviceAsset = service.asset.character;
const dictType = 'asset_character_type';
const categoryOptions = computed(() => dict.get(dictType).value ?? []);

const {
	viewMode,
	wallList,
	wallLoading,
	wallPage,
	refreshWall,
	switchView,
	statusOptions,
	statusColors,
	isMine,
	isAdmin,
	canEdit,
	canDelete,
	transition,
	fork,
	drawer,
	detailStats,
	openDetail,
	onUpsertOpened
} = useAssetLibrary(serviceAsset, {
	onChanged: () => Crud.value?.refresh()
});

const Crud = useCrud({ service: serviceAsset }, (app) => {
	app.refresh();
	if (viewMode.value === 'wall') refreshWall();
});

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
			width: 300,
			// 编辑/删除的行级权限在 slot 内判断（permission.mdc：操作列都要权限控制）
			buttons: ['slot-op']
		}
	],
	contextMenu: ['refresh']
});

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
		{ label: t('标识'), prop: 'code', group: 'base', component: { name: 'el-input', props: { placeholder: t('留空自动生成') } } },
		{ label: t('名称'), prop: 'name', group: 'base', required: true, component: { name: 'el-input' } },
		{
			label: t('角色类型'),
			prop: 'category',
			group: 'base',
			component: { name: 'dict-select', vm: markRaw(DictSelect), props: { dictType } }
		},
		{ label: t('封面'), prop: 'coverMediaId', group: 'base', component: { name: 'el-input', props: { placeholder: t('媒体资产 ID') } } },
		{
			label: t('外观正向 Prompt'),
			prop: 'appearancePrompt',
			group: 'prompt',
			// slot 内渲染输入框 + 变量槽只读预览（prop 必须是真实字段，cool-crud-conventions.mdc）
			component: { name: 'slot-appearancePrompt' }
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
		initRefImageForm(Upsert.value?.form as AssetUpsertForm | undefined);
	},
	onSubmit(data: AssetUpsertForm, { next }: { next: (payload: AssetUpsertForm) => void }) {
		const payload = buildSubmitPayload(data);
		payload.attributes = data.attributes || null;
		next(payload);
	},
	onOpened(data: AssetRow) {
		onUpsertOpened(data, Upsert.value?.form as AssetUpsertForm | undefined, () => Upsert.value?.close());
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
			<asset-card-wall
				:list="wallList"
				:loading="wallLoading"
				:dict-type="dictType"
				empty-text="暂无角色"
				@open="openDetail"
			/>
		</cl-row>

		<!-- 表格形态 -->
		<cl-row v-else>
			<cl-table ref="Table">
				<template #slot-op="{ scope }">
					<el-button v-if="canEdit(scope.row)" link type="primary" size="small" @click="openDetail(scope.row)">
						{{ $t('详情') }}
					</el-button>
					<el-button
						v-if="canEdit(scope.row)"
						v-permission="serviceAsset.permission.update"
						link
						type="primary"
						size="small"
						@click="Crud?.rowEdit(scope.row)"
					>
						{{ $t('编辑') }}
					</el-button>
					<el-button
						v-if="canDelete(scope.row)"
						v-permission="serviceAsset.permission.delete"
						link
						type="danger"
						size="small"
						@click="Crud?.rowDelete(scope.row)"
					>
						{{ $t('删除') }}
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
			<template #slot-appearancePrompt="{ scope }">
				<el-input
					v-model="scope.appearancePrompt"
					type="textarea"
					:rows="6"
					:placeholder="$t('唯一拼接源，支持双花括号变量占位（仅在资产片段内生效）')"
				/>
				<div class="var-slots">
					<el-tag v-for="name in varSlots" :key="name" size="small" class="slot">{{ name }}</el-tag>
					<span v-if="!varSlots.length" class="none">{{ $t('无变量占位') }}</span>
				</div>
			</template>
			<template #slot-refImages="{ scope }">
				<ref-image-manager
					:model-value="refImageModel(scope)"
					@update:model-value="refImageChange(scope, $event)"
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
.var-slots {
	display: flex;
	gap: 6px;
	flex-wrap: wrap;
	margin-top: 6px;
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
