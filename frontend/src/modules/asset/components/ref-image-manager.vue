<script setup lang="ts">
// 参考图集编辑（设计 5.1）：媒体库选图（返回 media id）+ 拖拽排序 + role 标记（核心仅 primary）+ 失效标注。
// 数据形态 {id, role?}[]；与后端 JSON 字符串的转换收在 upsert 表单 hook（upload.mdc 显式转换）。
import { computed, ref } from 'vue';
import { useAssetUrl, MediaImageSelect } from '/$/media';

export interface RefImageEntry {
	id: number;
	role?: string;
	_url?: string;
	_status?: string;
}

const props = defineProps<{
	modelValue: RefImageEntry[];
	max?: number;
}>();

const emit = defineEmits<{ (e: 'update:modelValue', value: RefImageEntry[]): void }>();

const { assetUrl } = useAssetUrl();
const selectVisible = ref(false);

const entries = computed(() => props.modelValue ?? []);

function emitEntries(list: RefImageEntry[]) {
	emit(
		'update:modelValue',
		list.map((e, i) => ({ ...e, role: i === 0 ? undefined : e.role }))
	);
}

function onMediaConfirm(items: { id: number; url: string }[]) {
	const existing = new Set(entries.value.map((e) => e.id));
	const addition = items
		.filter((it) => !existing.has(it.id))
		.slice(0, (props.max ?? 20) - entries.value.length)
		.map((it) => ({ id: it.id, _url: it.url }));
	if (addition.length) {
		emitEntries([...entries.value, ...addition]);
	}
}

function removeAt(index: number) {
	const list = [...entries.value];
	list.splice(index, 1);
	emitEntries(list);
}

function move(index: number, delta: number) {
	const target = index + delta;
	if (target < 0 || target >= entries.value.length) return;
	const list = [...entries.value];
	[list[index], list[target]] = [list[target], list[index]];
	emitEntries(list);
}

function srcOf(entry: RefImageEntry) {
	return entry._url ? assetUrl(entry._url) : '';
}
</script>

<template>
	<div class="ref-manager">
		<div class="list">
			<div v-for="(entry, index) in entries" :key="entry.id" class="item">
				<el-image v-if="entry._url" :src="srcOf(entry)" fit="cover" class="thumb">
					<template #error>
						<div class="broken">{{ $t('已失效') }}</div>
					</template>
				</el-image>
				<div v-else class="broken">{{ $t('已失效') }}</div>

				<div class="ops">
					<el-tag v-if="index === 0" size="small" type="success">{{ $t('首选') }}</el-tag>
					<el-button link size="small" :disabled="index === 0" @click="move(index, -1)">←</el-button>
					<el-button link size="small" :disabled="index === entries.length - 1" @click="move(index, 1)">→</el-button>
					<el-button link size="small" type="danger" @click="removeAt(index)">{{ $t('删除') }}</el-button>
				</div>
			</div>

			<div v-if="entries.length < (max ?? 20)" class="add" @click="selectVisible = true">＋</div>
		</div>

		<media-image-select v-model="selectVisible" multiple :title="$t('选择参考图')" @confirm="onMediaConfirm" />
	</div>
</template>

<style scoped>
.list {
	display: flex;
	flex-wrap: wrap;
	gap: 10px;
}
.item {
	width: 96px;
}
.thumb,
.broken {
	width: 96px;
	height: 96px;
	border-radius: 6px;
	display: flex;
	align-items: center;
	justify-content: center;
}
.broken {
	background: var(--el-fill-color-light);
	color: var(--el-text-color-secondary);
	font-size: 12px;
}
.ops {
	display: flex;
	align-items: center;
	justify-content: space-between;
	margin-top: 4px;
}
.ops .el-button {
	margin: 0;
	padding: 2px;
}
.add {
	width: 96px;
	height: 96px;
	border: 1px dashed var(--el-border-color);
	border-radius: 6px;
	display: flex;
	align-items: center;
	justify-content: center;
	font-size: 24px;
	cursor: pointer;
	color: var(--el-text-color-secondary);
}
.add:hover {
	border-color: var(--el-color-primary);
	color: var(--el-color-primary);
}
</style>
