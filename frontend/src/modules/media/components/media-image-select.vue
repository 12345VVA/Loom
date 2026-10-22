<script setup lang="ts">
// 媒体库选图（跨模块公共 API，经 /$/media 导出）：弹窗 + 图片网格 + 多选。
// 数据走 EPS service.media.asset.page（image/success 过滤）；展示走 useAssetUrl。
import { computed, reactive, ref, watch } from 'vue';
import { useCool } from '/@/cool';
import { useAssetUrl } from '/$/media';

export interface MediaImageItem {
	id: number;
	url: string;
	fileName?: string | null;
}

const props = defineProps<{
	modelValue: boolean;
	multiple?: boolean;
	title?: string;
}>();

const emit = defineEmits<{
	(e: 'update:modelValue', value: boolean): void;
	(e: 'confirm', items: MediaImageItem[]): void;
}>();

const { service } = useCool();
const { assetUrl } = useAssetUrl();

const visible = computed({
	get: () => props.modelValue,
	set: (v: boolean) => emit('update:modelValue', v)
});

const loading = ref(false);
const keyword = ref('');
const selected = ref<MediaImageItem[]>([]);
const list = ref<MediaImageItem[]>([]);
const page = reactive({ page: 1, size: 24, total: 0 });

async function refresh() {
	loading.value = true;
	try {
		const res = await service.media.asset.page({
			page: page.page,
			size: page.size,
			assetType: 'image',
			status: 'success',
			keyword: keyword.value || undefined
		});
		page.total = res.pagination.total;
		list.value = (res.list || [])
			.filter(row => row.id != null)
			.map(row => ({
				id: row.id as number,
				url: assetUrl(row.storageUrl || row.remoteUrl || ''),
				fileName: row.fileName
			}));
	} finally {
		loading.value = false;
	}
}

watch(visible, (v) => {
	if (v) {
		selected.value = [];
		page.page = 1;
		refresh();
	}
});

function toggle(item: MediaImageItem) {
	if (!props.multiple) {
		selected.value = [item];
		return;
	}
	const index = selected.value.findIndex((s) => s.id === item.id);
	if (index >= 0) {
		selected.value.splice(index, 1);
	} else {
		selected.value.push(item);
	}
}

function isSelected(item: MediaImageItem) {
	return selected.value.some((s) => s.id === item.id);
}

function onConfirm() {
	emit('confirm', [...selected.value]);
	visible.value = false;
}
</script>

<template>
	<el-dialog v-model="visible" :title="title || $t('从媒体库选择图片')" width="860px" append-to-body>
		<div class="media-select">
			<div class="toolbar">
				<el-input
					v-model="keyword"
					:placeholder="$t('搜索文件名')"
					clearable
					class="kw"
					@change="page.page = 1; refresh()"
				/>
				<span class="count">{{ $t('已选 {n} 项', { n: selected.length }) }}</span>
			</div>

			<div v-loading="loading" class="grid">
				<div
					v-for="item in list"
					:key="item.id"
					class="cell"
					:class="{ active: isSelected(item) }"
					@click="toggle(item)"
				>
					<el-image :src="item.url" fit="cover" lazy class="thumb" />
					<span v-if="isSelected(item)" class="badge">✓</span>
				</div>
				<el-empty v-if="!loading && !list.length" :description="$t('暂无图片')" />
			</div>

			<el-pagination
				v-model:current-page="page.page"
				:page-size="page.size"
				:total="page.total"
				layout="prev, pager, next"
				class="pager"
				@current-change="refresh"
			/>
		</div>

		<template #footer>
			<el-button @click="visible = false">{{ $t('取消') }}</el-button>
			<el-button type="primary" :disabled="!selected.length" @click="onConfirm">
				{{ $t('确定') }}
			</el-button>
		</template>
	</el-dialog>
</template>

<style scoped>
.media-select {
	display: flex;
	flex-direction: column;
	gap: 12px;
}
.toolbar {
	display: flex;
	align-items: center;
	gap: 12px;
}
.toolbar .kw {
	width: 240px;
}
.toolbar .count {
	margin-left: auto;
	color: var(--el-text-color-secondary);
}
.grid {
	display: grid;
	grid-template-columns: repeat(6, 1fr);
	gap: 10px;
	min-height: 240px;
	max-height: 420px;
	overflow: auto;
}
.cell {
	position: relative;
	aspect-ratio: 1;
	border-radius: 6px;
	overflow: hidden;
	cursor: pointer;
	border: 2px solid transparent;
}
.cell.active {
	border-color: var(--el-color-primary);
}
.thumb {
	width: 100%;
	height: 100%;
}
.badge {
	position: absolute;
	right: 4px;
	top: 4px;
	background: var(--el-color-primary);
	color: #fff;
	border-radius: 50%;
	width: 20px;
	height: 20px;
	display: flex;
	align-items: center;
	justify-content: center;
	font-size: 12px;
}
.pager {
	align-self: flex-end;
}
</style>
