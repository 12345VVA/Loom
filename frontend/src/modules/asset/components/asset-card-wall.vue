<script setup lang="ts">
// 封面墙卡片网格（三库共享，设计 5.2）：统一封面比例 + 懒加载 + 骨架屏 +
// 状态/他人悬浮标注 + 分类标注；点击卡片由父级打开详情。
import { computed } from 'vue';
import { useI18n } from 'vue-i18n';
import { useDict } from '/$/dict';
import { useUserStore } from '/$/base/store/user';
import type { AssetRow } from '../composables/use-asset-library';

const props = defineProps<{
	list: AssetRow[];
	loading?: boolean;
	dictType?: string;
	emptyText: string;
}>();

const emit = defineEmits<{ (e: 'open', row: AssetRow): void }>();

const { dict } = useDict();
const userStore = useUserStore();

// 状态枚举（键即 locale 键：草稿/已发布/已归档）
const statusLabels: Record<string, string> = { draft: '草稿', published: '已发布', archived: '已归档' };
const statusColors: Record<string, 'info' | 'success' | 'warning'> = {
	draft: 'info',
	published: 'success',
	archived: 'warning'
};

const categoryDict = computed(() => (props.dictType ? dict.get(props.dictType).value ?? [] : []));

function categoryLabel(row: AssetRow) {
	if (!row.category) return '';
	const item = categoryDict.value.find((o) => o.value === row.category);
	return item?.label ?? item?.name ?? '';
}

function isMine(row: AssetRow) {
	return !!row.createdBy && row.createdBy === userStore.info?.id;
}
</script>

<template>
	<div class="wall">
		<!-- 骨架屏 -->
		<template v-if="loading">
			<div v-for="i in 8" :key="'sk' + i" class="card sk">
				<el-skeleton-item variant="image" animated class="sk-cover" />
				<div class="info"><el-skeleton-item variant="text" animated class="sk-line lg" /></div>
				<div class="sub"><el-skeleton-item variant="text" animated class="sk-line sm" /></div>
			</div>
		</template>

		<template v-else>
			<div v-for="row in list" :key="row.id" class="card" @click="emit('open', row)">
				<div class="cover-wrap">
					<el-image :src="row.coverUrl || row.mediaItems?.[0]?.url" fit="cover" lazy class="cover">
						<template #error>
							<div class="cover-empty">{{ $t('无封面') }}</div>
						</template>
					</el-image>
					<el-tag class="mark status" size="small" :type="statusColors[row.status] || 'info'">
						{{ $t(statusLabels[row.status] || row.status) }}
					</el-tag>
					<el-tag v-if="!isMine(row)" class="mark owner" size="small" type="info" effect="plain">
						{{ $t('他人') }}
					</el-tag>
				</div>
				<div class="info">
					<span class="name" :title="row.name">{{ row.name }}</span>
					<span v-if="categoryLabel(row)" class="cat">{{ categoryLabel(row) }}</span>
				</div>
				<div class="sub">{{ row.code }}</div>
			</div>
			<el-empty v-if="!list.length" :description="$t(emptyText)" class="empty" />
		</template>
	</div>
</template>

<style scoped>
.wall {
	display: grid;
	grid-template-columns: repeat(auto-fill, minmax(180px, 1fr));
	gap: 14px;
	width: 100%;
	padding: 4px;
	min-height: 200px;
}
.empty {
	grid-column: 1 / -1;
}
.card {
	position: relative;
	border: 1px solid var(--el-border-color-lighter);
	border-radius: 8px;
	overflow: hidden;
	cursor: pointer;
	background: var(--el-bg-color);
	transition:
		box-shadow 0.2s,
		transform 0.2s,
		border-color 0.2s;
}
.card:hover {
	transform: translateY(-2px);
	box-shadow: var(--el-box-shadow-light);
	border-color: var(--el-color-primary-light-5);
}
.cover-wrap {
	position: relative;
	aspect-ratio: 4 / 3;
	background: var(--el-fill-color-light);
}
.cover {
	width: 100%;
	height: 100%;
	display: block;
}
.cover-empty {
	width: 100%;
	height: 100%;
	display: flex;
	align-items: center;
	justify-content: center;
	color: var(--el-text-color-secondary);
	font-size: 12px;
}
.mark {
	position: absolute;
	top: 8px;
}
.mark.status {
	right: 8px;
}
.mark.owner {
	left: 8px;
}
.info {
	display: flex;
	align-items: center;
	justify-content: space-between;
	gap: 8px;
	padding: 8px 10px 2px;
}
.name {
	font-weight: 500;
	overflow: hidden;
	text-overflow: ellipsis;
	white-space: nowrap;
}
.cat {
	flex-shrink: 0;
	max-width: 45%;
	overflow: hidden;
	text-overflow: ellipsis;
	white-space: nowrap;
	font-size: 12px;
	line-height: 18px;
	color: var(--el-color-primary);
	background: var(--el-color-primary-light-9);
	border-radius: 4px;
	padding: 0 6px;
}
.sub {
	padding: 2px 10px 8px;
	font-size: 12px;
	color: var(--el-text-color-secondary);
	font-family: ui-monospace, sfmono-regular, Menlo, Consolas, monospace;
	overflow: hidden;
	text-overflow: ellipsis;
	white-space: nowrap;
}
.sk-cover {
	width: 100%;
	aspect-ratio: 4 / 3;
	display: block;
	border-radius: 0;
}
.sk-line {
	height: 12px;
}
.sk-line.lg {
	width: 60%;
}
.sk-line.sm {
	width: 40%;
}
</style>
