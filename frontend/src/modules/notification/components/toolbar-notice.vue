<template>
	<el-popover
		v-if="canView"
		v-model:visible="visible"
		placement="bottom-end"
		width="360"
		trigger="click"
		popper-class="notification-toolbar-popper"
		@show="refresh"
	>
		<template #reference>
			<div class="cl-comm__icon" :title="$t('通知')">
				<el-badge :value="unreadCount" :hidden="unreadCount <= 0" :max="99">
					<cl-svg name="icon-notification" />
				</el-badge>
			</div>
		</template>

		<div class="notification-toolbar">
			<div class="notification-toolbar__header">
				<span>{{ $t('通知') }}</span>
				<el-button
					link
					type="primary"
					size="small"
					:disabled="unreadCount <= 0"
					@click="readAll"
				>
					{{ $t('全部已读') }}
				</el-button>
			</div>

			<el-scrollbar max-height="360px">
				<div v-if="list.length" class="notification-toolbar__list">
					<div
						v-for="item in list"
						:key="item.id"
						class="notification-toolbar__item"
						:class="{ 'is-unread': !item.isRead }"
						@click="showDetail(item)"
					>
						<div class="main">
							<p class="title">{{ item.title }}</p>
							<p class="content">{{ item.content }}</p>
							<span class="time">{{ item.createTime || item.createdAt }}</span>
						</div>

						<el-button
							link
							size="small"
							type="info"
							@click.stop="archive(item)"
						>
							{{ $t('归档') }}
						</el-button>
					</div>
				</div>

				<el-empty v-else :description="$t('暂无通知')" :image-size="80" />
			</el-scrollbar>

			<div class="notification-toolbar__footer">
				<el-button link type="primary" @click="goCenter">
					{{ $t('查看全部') }}
				</el-button>
			</div>
		</div>

		<el-dialog v-model="detail.visible" :title="detail.item?.title" width="520px">
			<template v-if="detail.item">
				<div class="notification-toolbar__detail">
					<p>{{ detail.item.content }}</p>
					<el-descriptions :column="1" border>
						<el-descriptions-item :label="$t('类型')">
							{{ detail.item.messageType || '-' }}
						</el-descriptions-item>
						<el-descriptions-item :label="$t('级别')">
							{{ detail.item.level || '-' }}
						</el-descriptions-item>
						<el-descriptions-item :label="$t('创建时间')">
							{{ detail.item.createTime || detail.item.createdAt || '-' }}
						</el-descriptions-item>
					</el-descriptions>
				</div>
			</template>
			<template #footer>
				<el-button @click="detail.visible = false">{{ $t('关闭') }}</el-button>
				<el-button v-if="detail.item?.linkUrl" type="primary" @click="goLink(detail.item)">
					{{ $t('前往处理') }}
				</el-button>
			</template>
		</el-dialog>
	</el-popover>
</template>

<script lang="ts" setup>
defineOptions({
	name: 'notification-toolbar-notice'
});

import { computed, onBeforeUnmount, onMounted, reactive, ref } from 'vue';
import { useCool } from '/@/cool';

type NoticeItem = {
	id: number;
	title: string;
	content: string;
	linkUrl?: string;
	isRead?: boolean;
	createTime?: string;
	createdAt?: string;
	messageType?: string;
	level?: string;
};

const { service, router } = useCool();
const visible = ref(false);
const unreadCount = ref(0);
const list = ref<NoticeItem[]>([]);
const detail = reactive<{ visible: boolean; item?: NoticeItem }>({
	visible: false
});
let timer: ReturnType<typeof window.setInterval> | null = null;

const canView = computed(() => {
	return service.notification.message._permission?.mine !== false;
});

async function refreshCount() {
	if (!canView.value) {
		return;
	}

	const res = await service.notification.message.unreadCount();
	unreadCount.value = Number(res?.count || 0);
}

async function refresh() {
	if (!canView.value) {
		return;
	}

	const res = await service.notification.message.mine({ includeArchived: false, readStatus: 'unread' });
	list.value = (res || []).slice(0, 8);
	await refreshCount();
}

async function showDetail(item: NoticeItem) {
	if (!item.isRead) {
		await service.notification.message.read({ ids: [item.id] });
		item.isRead = true;
		await refreshCount();
	}
	detail.item = await service.notification.message.myInfo({ id: item.id });
	detail.visible = true;
	await refresh();
}

function goLink(item: NoticeItem) {
	detail.visible = false;
	visible.value = false;
	if (item.linkUrl) {
		router.push(item.linkUrl);
	}
}

async function readAll() {
	await service.notification.message.readAll();
	await refresh();
}

async function archive(item: NoticeItem) {
	await service.notification.message.archive({ ids: [item.id] });
	await refresh();
}

function goCenter() {
	visible.value = false;
	router.push('/my/notification');
}

onMounted(() => {
	refreshCount();
	timer = window.setInterval(refreshCount, 60000);
});

onBeforeUnmount(() => {
	if (timer) {
		window.clearInterval(timer);
	}
});
</script>

<style lang="scss" scoped>
.notification-toolbar {
	&__header,
	&__footer {
		display: flex;
		align-items: center;
		justify-content: space-between;
	}

	&__header {
		padding-bottom: 10px;
		font-weight: 600;
		border-bottom: 1px solid var(--el-border-color-lighter);
	}

	&__list {
		padding: 4px 0;
	}

	&__item {
		display: flex;
		align-items: flex-start;
		gap: 8px;
		padding: 10px 0;
		border-bottom: 1px solid var(--el-border-color-extra-light);
		cursor: pointer;

		&:last-child {
			border-bottom: 0;
		}

		&.is-unread {
			.title::before {
				content: '';
				display: inline-block;
				width: 6px;
				height: 6px;
				margin-right: 6px;
				border-radius: 50%;
				background-color: var(--el-color-primary);
				vertical-align: middle;
			}
		}

		.main {
			min-width: 0;
			flex: 1;
		}

		.title,
		.content {
			margin: 0;
			overflow: hidden;
			text-overflow: ellipsis;
			white-space: nowrap;
		}

		.title {
			font-size: 13px;
			color: var(--el-text-color-primary);
		}

		.content {
			margin-top: 4px;
			font-size: 12px;
			color: var(--el-text-color-secondary);
		}

		.time {
			display: block;
			margin-top: 6px;
			font-size: 11px;
			color: var(--el-text-color-placeholder);
		}
	}

	&__footer {
		justify-content: center;
		padding-top: 8px;
		border-top: 1px solid var(--el-border-color-lighter);
	}

	&__detail {
		p {
			margin: 0 0 16px;
			line-height: 1.7;
			white-space: pre-wrap;
		}
	}
}
</style>
