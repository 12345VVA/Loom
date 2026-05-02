<template>
	<div class="my-notification">
		<div class="my-notification__header">
			<div>
				<h3>{{ $t('我的通知') }}</h3>
				<p>{{ $t('查看系统通知、业务通知和任务通知') }}</p>
			</div>

			<div class="actions">
				<el-segmented v-model="filter" :options="filterOptions" @change="refresh" />
				<el-button @click="refresh">{{ $t('刷新') }}</el-button>
				<el-button type="primary" :disabled="unreadCount <= 0" @click="readAll">
					{{ $t('全部已读') }}
				</el-button>
			</div>
		</div>

		<el-scrollbar>
			<div v-if="list.length" class="my-notification__list">
				<div
					v-for="item in list"
					:key="item.id"
					class="notice"
					:class="{ 'is-unread': !item.isRead, 'is-archived': item.isArchived }"
				>
					<div class="notice__content" @click="showDetail(item)">
						<div class="notice__title">
							<span>{{ item.title }}</span>
							<el-tag v-if="!item.isRead" size="small" type="primary">
								{{ $t('未读') }}
							</el-tag>
							<el-tag v-if="item.isArchived" size="small" type="info">
								{{ $t('已归档') }}
							</el-tag>
						</div>
						<p>{{ item.content }}</p>
						<div class="notice__meta">
							<span>{{ item.messageType || $t('通知') }}</span>
							<span>{{ item.level || 'info' }}</span>
							<span>{{ item.createTime || item.createdAt }}</span>
						</div>
					</div>

					<div class="notice__actions">
						<el-button v-if="!item.isRead" link type="primary" @click="markRead(item)">
							{{ $t('标记已读') }}
						</el-button>
						<el-button v-if="!item.isArchived" link type="info" @click="archive(item)">
							{{ $t('归档') }}
						</el-button>
						<el-button v-else link type="primary" @click="unarchive(item)">
							{{ $t('取消归档') }}
						</el-button>
					</div>
				</div>
			</div>

			<el-empty v-else :description="$t('暂无通知')" />
		</el-scrollbar>

		<el-dialog v-model="detail.visible" :title="detail.item?.title" width="560px">
			<template v-if="detail.item">
				<div class="notification-detail">
					<p class="content">{{ detail.item.content }}</p>
					<el-descriptions :column="1" border>
						<el-descriptions-item :label="$t('类型')">
							{{ detail.item.messageType || '-' }}
						</el-descriptions-item>
						<el-descriptions-item :label="$t('级别')">
							{{ detail.item.level || '-' }}
						</el-descriptions-item>
						<el-descriptions-item :label="$t('来源模块')">
							{{ detail.item.sourceModule || '-' }}
						</el-descriptions-item>
						<el-descriptions-item :label="$t('业务键')">
							{{ detail.item.businessKey || '-' }}
						</el-descriptions-item>
						<el-descriptions-item :label="$t('创建时间')">
							{{ detail.item.createTime || detail.item.createdAt || '-' }}
						</el-descriptions-item>
						<el-descriptions-item :label="$t('读取时间')">
							{{ detail.item.readTime || '-' }}
						</el-descriptions-item>
					</el-descriptions>
				</div>
			</template>

			<template #footer>
				<el-button @click="detail.visible = false">{{ $t('关闭') }}</el-button>
				<el-button
					v-if="detail.item?.linkUrl"
					type="primary"
					@click="goLink(detail.item)"
				>
					{{ $t('前往处理') }}
				</el-button>
			</template>
		</el-dialog>
	</div>
</template>

<script lang="ts" setup>
defineOptions({
	name: 'my-notification'
});

import { ElMessage } from 'element-plus';
import { computed, onMounted, reactive, ref } from 'vue';
import { useCool } from '/@/cool';
import { useI18n } from 'vue-i18n';

type NoticeItem = {
	id: number;
	title: string;
	content: string;
	messageType?: string;
	level?: string;
	linkUrl?: string;
	sourceModule?: string;
	businessKey?: string;
	isRead?: boolean;
	isArchived?: boolean;
	readTime?: string;
	createTime?: string;
	createdAt?: string;
};

const { service, router } = useCool();
const { t } = useI18n();
const list = ref<NoticeItem[]>([]);
const unreadCount = ref(0);
const filter = ref('all');
const detail = reactive<{ visible: boolean; item?: NoticeItem }>({
	visible: false
});
const filterOptions = computed(() => [
	{ label: t('全部'), value: 'all' },
	{ label: t('未读'), value: 'unread' },
	{ label: t('系统'), value: 'system' },
	{ label: t('业务'), value: 'business' },
	{ label: t('任务'), value: 'task' },
	{ label: t('已归档'), value: 'archived' }
]);

async function refreshCount() {
	const res = await service.notification.message.unreadCount();
	unreadCount.value = Number(res?.count || 0);
}

async function refresh() {
	const query: any = {
		includeArchived: filter.value === 'archived'
	};
	if (filter.value === 'unread') {
		query.readStatus = 'unread';
	} else if (filter.value === 'archived') {
		query.readStatus = 'archived';
	} else if (['system', 'business', 'task'].includes(filter.value)) {
		query.messageType = filter.value;
	}
	const res = await service.notification.message.mine({
		...query
	});
	list.value = res || [];
	await refreshCount();
}

async function markRead(item: NoticeItem) {
	await service.notification.message.read({ ids: [item.id] });
	ElMessage.success(t('操作成功'));
	await refresh();
}

async function readAll() {
	await service.notification.message.readAll();
	ElMessage.success(t('操作成功'));
	await refresh();
}

async function archive(item: NoticeItem) {
	await service.notification.message.archive({ ids: [item.id] });
	ElMessage.success(t('操作成功'));
	await refresh();
}

async function unarchive(item: NoticeItem) {
	await service.notification.message.unarchive({ ids: [item.id] });
	ElMessage.success(t('操作成功'));
	await refresh();
}

async function showDetail(item: NoticeItem) {
	if (!item.isRead) {
		await service.notification.message.read({ ids: [item.id] });
		await refreshCount();
	}
	detail.item = await service.notification.message.myInfo({ id: item.id });
	detail.visible = true;
	await refresh();
}

function goLink(item: NoticeItem) {
	detail.visible = false;
	if (item.linkUrl) {
		router.push(item.linkUrl);
	}
}

onMounted(() => {
	refresh();
});
</script>

<style lang="scss" scoped>
.my-notification {
	height: 100%;
	padding: 20px;
	box-sizing: border-box;
	background-color: var(--el-bg-color-page);

	&__header {
		display: flex;
		align-items: center;
		justify-content: space-between;
		margin-bottom: 16px;

		h3,
		p {
			margin: 0;
		}

		h3 {
			font-size: 18px;
			color: var(--el-text-color-primary);
		}

		p {
			margin-top: 6px;
			font-size: 13px;
			color: var(--el-text-color-secondary);
		}

		.actions {
			display: flex;
			align-items: center;
			gap: 10px;
		}
	}

	&__list {
		display: flex;
		flex-direction: column;
		gap: 10px;
	}

	.notice {
		display: flex;
		align-items: flex-start;
		justify-content: space-between;
		padding: 16px;
		border: 1px solid var(--el-border-color-lighter);
		border-radius: 6px;
		background-color: var(--el-bg-color);

		&.is-unread {
			border-color: var(--el-color-primary-light-7);
			background-color: var(--el-color-primary-light-9);
		}

		&.is-archived {
			opacity: 0.72;
		}

		&__content {
			min-width: 0;
			flex: 1;
			cursor: pointer;

			p {
				margin: 8px 0;
				color: var(--el-text-color-regular);
				line-height: 1.6;
			}
		}

		&__title {
			display: flex;
			align-items: center;
			gap: 8px;
			font-weight: 600;
			color: var(--el-text-color-primary);
		}

		&__meta {
			display: flex;
			flex-wrap: wrap;
			gap: 12px;
			font-size: 12px;
			color: var(--el-text-color-secondary);
		}

		&__actions {
			display: flex;
			align-items: center;
			margin-left: 16px;
		}
	}

	.notification-detail {
		.content {
			margin: 0 0 16px;
			line-height: 1.7;
			white-space: pre-wrap;
			color: var(--el-text-color-regular);
		}
	}
}
</style>
