<template>
	<div class="notification-workbench">
		<div class="stats">
			<div v-for="item in statCards" :key="item.label" class="stat">
				<span>{{ item.label }}</span>
				<strong>{{ item.value }}</strong>
			</div>
		</div>

		<cl-crud ref="Crud">
			<cl-row>
				<el-button type="primary" @click="openSend">{{ $t('发送通知') }}</el-button>
				<cl-refresh-btn />
				<cl-multi-delete-btn />
				<cl-flex1 />
				<el-select v-model="filters.messageType" clearable :placeholder="$t('类型')" @change="refresh">
					<el-option label="system" value="system" />
					<el-option label="business" value="business" />
					<el-option label="task" value="task" />
				</el-select>
				<el-select v-model="filters.level" clearable :placeholder="$t('级别')" @change="refresh">
					<el-option label="info" value="info" />
					<el-option label="success" value="success" />
					<el-option label="warning" value="warning" />
					<el-option label="error" value="error" />
				</el-select>
				<cl-search-key :placeholder="$t('搜索标题、内容')" />
			</cl-row>

			<cl-row>
				<cl-table ref="Table" />
			</cl-row>

			<cl-row>
				<cl-flex1 />
				<cl-pagination />
			</cl-row>
		</cl-crud>

		<el-dialog v-model="send.visible" :title="$t('发送通知')" width="760px">
			<el-steps :active="send.step" finish-status="success" simple>
				<el-step :title="$t('填写内容')" />
				<el-step :title="$t('选择受众')" />
				<el-step :title="$t('确认发送')" />
			</el-steps>

			<div class="send-body">
				<el-form v-if="send.step === 0" label-position="top" :model="send.form">
					<el-form-item :label="$t('标题')" required>
						<el-input v-model="send.form.title" />
					</el-form-item>
					<el-form-item :label="$t('内容')" required>
						<el-input v-model="send.form.content" type="textarea" :rows="5" />
					</el-form-item>
					<el-form-item :label="$t('类型')">
						<el-select v-model="send.form.messageType" class="w-full">
							<el-option label="system" value="system" />
							<el-option label="business" value="business" />
							<el-option label="task" value="task" />
						</el-select>
					</el-form-item>
					<el-form-item :label="$t('级别')">
						<el-select v-model="send.form.level" class="w-full">
							<el-option label="info" value="info" />
							<el-option label="success" value="success" />
							<el-option label="warning" value="warning" />
							<el-option label="error" value="error" />
						</el-select>
					</el-form-item>
					<el-form-item :label="$t('来源模块')">
						<el-input v-model="send.form.sourceModule" />
					</el-form-item>
					<el-form-item :label="$t('业务键')">
						<el-input v-model="send.form.businessKey" />
					</el-form-item>
					<el-form-item :label="$t('跳转链接')">
						<el-input v-model="send.form.linkUrl" />
					</el-form-item>
				</el-form>

				<notification-audience-editor v-if="send.step === 1" v-model="send.form.audience" />

				<div v-if="send.step === 2" class="confirm">
					<el-alert
						:title="$t('预计接收人数') + ': ' + preview.count"
						type="info"
						show-icon
						:closable="false"
					/>
					<el-descriptions :column="1" border class="mt">
						<el-descriptions-item :label="$t('标题')">{{ send.form.title }}</el-descriptions-item>
						<el-descriptions-item :label="$t('内容')">{{ send.form.content }}</el-descriptions-item>
						<el-descriptions-item :label="$t('类型')">{{ send.form.messageType }}</el-descriptions-item>
						<el-descriptions-item :label="$t('级别')">{{ send.form.level }}</el-descriptions-item>
					</el-descriptions>
				</div>
			</div>

			<template #footer>
				<el-button @click="send.visible = false">{{ $t('取消') }}</el-button>
				<el-button v-if="send.step > 0" @click="send.step--">{{ $t('上一步') }}</el-button>
				<el-button v-if="send.step < 2" type="primary" @click="nextStep">
					{{ $t('下一步') }}
				</el-button>
				<el-button v-else type="primary" @click="submitSend">{{ $t('确认发送') }}</el-button>
			</template>
		</el-dialog>

		<el-dialog v-model="detail.visible" :title="detail.item?.title" width="620px">
			<p class="detail-content">{{ detail.item?.content }}</p>
			<el-descriptions v-if="detail.item" :column="1" border>
				<el-descriptions-item :label="$t('类型')">{{ detail.item.messageType }}</el-descriptions-item>
				<el-descriptions-item :label="$t('级别')">{{ detail.item.level }}</el-descriptions-item>
				<el-descriptions-item :label="$t('来源模块')">{{ detail.item.sourceModule || '-' }}</el-descriptions-item>
				<el-descriptions-item :label="$t('撤回')">{{ detail.item.isRecalled ? $t('是') : $t('否') }}</el-descriptions-item>
			</el-descriptions>
		</el-dialog>

		<el-dialog v-model="recipients.visible" :title="$t('接收人明细')" width="720px">
			<el-table :data="recipients.list" height="420">
				<el-table-column prop="username" :label="$t('账号')" min-width="140" />
				<el-table-column prop="name" :label="$t('名称')" min-width="140" />
				<el-table-column prop="isRead" :label="$t('已读')" width="90" />
				<el-table-column prop="readTime" :label="$t('读取时间')" min-width="170" />
				<el-table-column prop="isArchived" :label="$t('归档')" width="90" />
			</el-table>
		</el-dialog>
	</div>
</template>

<script lang="ts" setup>
defineOptions({
	name: 'notification-message'
});

import { computed, reactive } from 'vue';
import { useCrud, useTable } from '@cool-vue/crud';
import { ElMessage, ElMessageBox } from 'element-plus';
import { useCool } from '/@/cool';
import { useI18n } from 'vue-i18n';
import NotificationAudienceEditor from '../components/audience-editor.vue';

const { service } = useCool();
const { t } = useI18n();
const stats = reactive({
	messageCount: 0,
	recipientCount: 0,
	readCount: 0,
	unreadCount: 0,
	recalledCount: 0,
	readRate: 0
});
const filters = reactive({
	messageType: '',
	level: ''
});
const send = reactive({
	visible: false,
	step: 0,
	form: defaultSendForm()
});
const preview = reactive({ count: 0, sample: [] as any[] });
const detail = reactive<{ visible: boolean; item?: any }>({ visible: false });
const recipients = reactive<{ visible: boolean; list: any[] }>({ visible: false, list: [] });
let crudApp: any;

const statCards = computed(() => [
	{ label: t('通知数'), value: stats.messageCount },
	{ label: t('接收人数'), value: stats.recipientCount },
	{ label: t('已读'), value: stats.readCount },
	{ label: t('未读'), value: stats.unreadCount },
	{ label: t('已读率'), value: `${stats.readRate}%` }
]);

const Table = useTable({
	columns: [
		{ type: 'selection' },
		{ label: t('标题'), prop: 'title', minWidth: 220, showOverflowTooltip: true },
		{ label: t('类型'), prop: 'messageType', width: 110 },
		{ label: t('级别'), prop: 'level', width: 100 },
		{ label: t('来源模块'), prop: 'sourceModule', width: 130 },
		{ label: t('发送状态'), prop: 'sendStatus', width: 110 },
		{ label: t('撤回'), prop: 'isRecalled', width: 90 },
		{ label: t('创建时间'), prop: 'createTime', sortable: 'desc', minWidth: 170 },
		{
			type: 'op',
			width: 250,
			buttons: [
				{ label: t('详情'), onClick: ({ scope }: any) => openDetail(scope.row) },
				{ label: t('接收人'), onClick: ({ scope }: any) => openRecipients(scope.row) },
				{
					label: t('撤回'),
					onClick: ({ scope }: any) => recall(scope.row)
				},
				'delete'
			]
		}
	]
});

const Crud = useCrud(
	{
		service: service.notification.message
	},
	app => {
		crudApp = app;
		refreshStats();
		app.refresh();
	}
);

function defaultSendForm() {
	return {
		title: '',
		content: '',
		messageType: 'business',
		level: 'info',
		sourceModule: '',
		businessKey: '',
		linkUrl: '',
		audience: {
			users: [],
			roles: [],
			departments: [],
			tenants: [],
			includeChildDepartments: true,
			allAdmins: true
		}
	};
}

function refresh() {
	crudApp?.refresh({
		messageType: filters.messageType || undefined,
		level: filters.level || undefined
	});
	refreshStats();
}

async function refreshStats() {
	Object.assign(stats, await service.notification.message.stats());
}

function openSend() {
	send.step = 0;
	send.form = defaultSendForm();
	preview.count = 0;
	preview.sample = [];
	send.visible = true;
}

async function nextStep() {
	if (send.step === 0 && (!send.form.title || !send.form.content)) {
		return ElMessage.warning(t('请填写标题和内容'));
	}
	if (send.step === 1) {
		Object.assign(preview, await service.notification.message.previewRecipients({
			audience: send.form.audience
		}));
	}
	send.step++;
}

async function submitSend() {
	await service.notification.message.send(send.form);
	ElMessage.success(t('发送成功'));
	send.visible = false;
	refresh();
}

function openDetail(row: any) {
	detail.item = row;
	detail.visible = true;
}

async function openRecipients(row: any) {
	recipients.list = await service.notification.message.recipients({ id: row.id });
	recipients.visible = true;
}

async function recall(row: any) {
	await ElMessageBox.confirm(t('撤回后用户侧将不再显示该通知，是否继续？'), t('提示'), {
		type: 'warning'
	});
	await service.notification.message.recall({ id: row.id });
	ElMessage.success(t('操作成功'));
	refresh();
}
</script>

<style lang="scss" scoped>
.notification-workbench {
	height: 100%;
	padding: 16px;
	box-sizing: border-box;
	background-color: var(--el-bg-color-page);

	.stats {
		display: grid;
		grid-template-columns: repeat(5, minmax(120px, 1fr));
		gap: 12px;
		margin-bottom: 12px;
	}

	.stat {
		padding: 14px;
		border-radius: 6px;
		background-color: var(--el-bg-color);
		border: 1px solid var(--el-border-color-lighter);

		span {
			display: block;
			font-size: 12px;
			color: var(--el-text-color-secondary);
		}

		strong {
			display: block;
			margin-top: 8px;
			font-size: 22px;
			color: var(--el-text-color-primary);
		}
	}

	.send-body {
		margin-top: 18px;
	}

	.w-full {
		width: 100%;
	}

	.mt {
		margin-top: 12px;
	}

	.detail-content {
		white-space: pre-wrap;
		line-height: 1.7;
	}
}
</style>
