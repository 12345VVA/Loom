<template>
	<cl-crud ref="Crud">
		<cl-row>
			<cl-add-btn :label="t('agent.profile.add')" />
		</cl-row>

		<cl-row>
			<cl-table ref="Table" />
		</cl-row>

		<cl-row>
			<cl-flex1 />
			<cl-pagination />
		</cl-row>

		<cl-upsert ref="Upsert" />

		<!-- 调试台 drawer（draft 试聊，SSE） -->
		<cl-drawer v-model="debugVisible" :title="t('agent.debug.title')" size="55%">
			<div class="debug-panel">
				<div class="debug-messages">
					<div v-if="!debugMessages.length && !debugRunning" class="debug-empty">
						{{ t('agent.debug.empty') }}
					</div>
					<ChatMessage v-for="(m, i) in debugMessages" :key="m.id || i" :message="m" />
					<div v-if="debugRunningTool" class="live-tool">
						<el-icon class="is-loading"><Loading /></el-icon>
						{{ t('agent.session.toolRunning') }}：{{ debugRunningTool.toolName }}
					</div>
					<div v-if="debugRunning && debugStreamingText" class="streaming">{{ debugStreamingText }}</div>
					<el-alert v-if="debugStopHint" :title="debugStopHint" type="warning" :closable="false" />
				</div>
				<div class="debug-input">
					<el-input
						v-model="debugInput"
						type="textarea"
						:rows="2"
						:disabled="debugRunning"
						:placeholder="t('agent.debug.inputPlaceholder')"
					/>
					<div class="debug-actions">
						<el-button v-if="debugRunning" type="danger" size="small" @click="debugStop()">
							{{ t('agent.session.stop') }}
						</el-button>
						<el-button v-else type="primary" size="small" :disabled="!debugInput.trim()" @click="sendDebug">
							{{ t('agent.debug.send') }}
						</el-button>
					</div>
				</div>
			</div>
		</cl-drawer>

		<!-- 版本列表 drawer -->
		<cl-drawer v-model="versionVisible" :title="t('agent.version.title')" size="45%">
			<el-table :data="versions" size="small">
				<el-table-column prop="version" :label="t('agent.version.no')" width="70" />
				<el-table-column prop="createTime" :label="t('agent.version.time')" width="170" />
				<el-table-column prop="snapshotHash" :label="t('agent.version.hash')">
					<template #default="{ row }">
						<span class="hash-text">{{ (row.snapshotHash || '').slice(0, 12) }}</span>
					</template>
				</el-table-column>
				<el-table-column :label="t('agent.version.ops')" width="90">
					<template #default="{ row }">
						<el-button link type="primary" size="small" @click="onRollback(row)">
							{{ t('agent.profile.rollback') }}
						</el-button>
					</template>
				</el-table-column>
			</el-table>
		</cl-drawer>
	</cl-crud>
</template>

<script lang="ts" setup name="agent-profile">
import { onMounted, ref } from 'vue';
import { useCrud, useTable, useUpsert } from '@cool-vue/crud';
import { useI18n } from 'vue-i18n';
import { ElMessage, ElMessageBox } from 'element-plus';
import { Loading } from '@element-plus/icons-vue';
import { useCool } from '/@/cool';
import ChatMessage from '../components/chat-message.vue';
import { useAgentSession } from '../composables/use-agent-session';

const { service } = useCool();
const { t } = useI18n();
const serviceAgent = service.agent.profile;

// 表单选项（EPS options 仅支持响应式数组——挂载时预载，workflow_eval case.vue 先例）
const channelOptions = ref<any[]>([]);
const toolOptions = ref<any[]>([]);
onMounted(async () => {
	try {
		const channels = await service.ai.profile.list();
		channelOptions.value = (channels || []).map((p: any) => ({ label: p.name, value: p.code }));
	} catch {
		channelOptions.value = [];
	}
	try {
		const tools = await service.agent.tool.list();
		toolOptions.value = (tools || []).map((tool: any) => ({
			label: `${tool.displayName || tool.toolName}（${tool.level}）`,
			value: tool.toolName
		}));
	} catch {
		toolOptions.value = [];
	}
});

// 调试台（draft 模式共享 useAgentSession；解构后模板顶层自动解包）
const debug = useAgentSession({ mode: 'draft' });
const {
	messages: debugMessages,
	running: debugRunning,
	runningTool: debugRunningTool,
	streamingText: debugStreamingText,
	stopHint: debugStopHint,
	currentProfileId: debugProfileIdRef,
	send: debugSend,
	stop: debugStop
} = debug;

const debugVisible = ref(false);
const debugInput = ref('');
const debugProfileId = ref<number | null>(null);

async function sendDebug() {
	const question = debugInput.value.trim();
	if (!question || debugRunning.value) return;
	debugInput.value = '';
	debugProfileIdRef.value = debugProfileId.value ?? undefined;
	await debugSend(question);
}

// 版本列表
const versionVisible = ref(false);
const versions = ref<any[]>([]);
const versionProfileId = ref<number | null>(null);

async function openVersions(row: any) {
	versionProfileId.value = row.id;
	versions.value = ((await serviceAgent.versions({ id: row.id })) || []) as any[];
	versionVisible.value = true;
}

async function onRollback(row: any) {
	await ElMessageBox.confirm(t('agent.version.rollbackConfirm'), t('agent.version.title'), {
		type: 'warning'
	});
	if (!versionProfileId.value) return;
	await serviceAgent.rollback({ id: versionProfileId.value, snapshotId: row.id });
	ElMessage.success(t('agent.profile.rollbackSuccess'));
	versions.value = ((await serviceAgent.versions({ id: versionProfileId.value })) || []) as any[];
}

// ---- 表格形态 ----
const Table = useTable({
	columns: [
		{ type: 'index', label: '#', width: 50 },
		{ label: t('agent.profile.code'), prop: 'code', minWidth: 130 },
		{ label: t('agent.profile.name'), prop: 'name', minWidth: 130 },
		{ label: t('agent.profile.modelProfile'), prop: 'modelProfileCode', minWidth: 120 },
		{
			label: t('agent.profile.tools'),
			prop: 'tools',
			minWidth: 150,
			formatter: (row: any) => (Array.isArray(row.tools) ? row.tools.join('、') : row.tools || '-')
		},
		{ label: t('agent.profile.status'), prop: 'status', width: 90, tag: true, flex: false },
		{
			label: t('agent.profile.enabled'),
			prop: 'enabled',
			width: 80,
			flex: false,
			formatter: (row: any) => (row.enabled ? t('agent.profile.enabledOn') : t('agent.profile.enabledOff'))
		},
		{ label: t('agent.profile.createTime'), prop: 'createTime', width: 160, flex: false },
		{
			type: 'op',
			width: 300,
			buttons: [
				({ row }: any) => ({
					label: t('agent.profile.debug'),
					onClick: () => openDebug(row)
				}),
				({ row }: any) => ({
					label: t('agent.profile.publish'),
					hidden: row.status !== 'draft',
					onClick: () => onPublish(row)
				}),
				({ row }: any) => ({
					label: t('agent.profile.versions'),
					hidden: row.status !== 'published',
					onClick: () => openVersions(row)
				}),
				({ row }: any) => ({
					label: row.enabled ? t('agent.profile.disable') : t('agent.profile.enable'),
					onClick: () => onToggle(row)
				}),
				'edit',
				'delete'
			]
		}
	],
	contextMenu: ['refresh']
});

// ---- upsert ----
const Upsert = useUpsert({
	dialog: { width: '860px' },
	items: [
		{
			label: t('agent.profile.name'),
			prop: 'name',
			required: true,
			span: 12
		},
		{
			label: t('agent.profile.code'),
			prop: 'code',
			span: 12,
			component: { name: 'el-input', props: { placeholder: t('agent.profile.codePlaceholder') } }
		},
		{
			label: t('agent.profile.modelProfile'),
			prop: 'modelProfileCode',
			required: true,
			span: 12,
			component: {
				name: 'el-select',
				options: channelOptions,
				props: { placeholder: t('agent.profile.modelProfilePlaceholder') }
			}
		},
		{
			label: t('agent.profile.description'),
			prop: 'description',
			span: 12,
			component: { name: 'el-input' }
		},
		{
			label: t('agent.profile.systemPrompt'),
			prop: 'systemPrompt',
			component: {
				name: 'el-input',
				props: { type: 'textarea', rows: 6, placeholder: t('agent.profile.systemPromptPlaceholder') }
			}
		},
		{
			label: t('agent.profile.tools'),
			prop: 'tools',
			component: {
				name: 'el-select',
				options: toolOptions,
				props: { multiple: true, placeholder: t('agent.profile.toolsPlaceholder') }
			}
		},
		{
			label: t('agent.profile.temperature'),
			prop: 'temperature',
			span: 12,
			value: 0.5,
			component: { name: 'el-input-number', props: { min: 0, max: 2, step: 0.1 } }
		},
		{
			label: t('agent.profile.maxTokens'),
			prop: 'maxTokens',
			span: 12,
			value: 4000,
			component: { name: 'el-input-number', props: { min: 256, max: 26000, step: 256 } }
		},
		{
			label: t('agent.profile.maxToolRounds'),
			prop: 'maxToolRounds',
			span: 12,
			value: 12,
			component: { name: 'el-input-number', props: { min: 1, max: 50 } }
		},
		{
			label: t('agent.profile.timeoutSeconds'),
			prop: 'timeoutSeconds',
			span: 12,
			value: 60,
			component: { name: 'el-input-number', props: { min: 10, max: 600 } }
		},
		{
			label: t('agent.profile.enableMemory'),
			prop: 'enableMemory',
			span: 12,
			value: true,
			flex: false,
			component: { name: 'el-switch' }
		}
	],
	onOpened(data: any) {
		debugProfileId.value = data.id ?? null;
	}
});

const Crud = useCrud({ service: serviceAgent }, (app) => {
	app.service.refresh();
});

async function openDebug(row: any) {
	debugProfileId.value = row.id;
	debugProfileIdRef.value = row.id;
	debug.newSession();
	debugVisible.value = true;
}

async function onPublish(row: any) {
	await ElMessageBox.confirm(t('agent.profile.publishConfirm'), t('agent.profile.publish'), {
		type: 'info'
	});
	const res = await serviceAgent.publish({ id: row.id });
	ElMessage.success(`${t('agent.profile.publishSuccess')} v${res.version}`);
	Crud.value?.refresh();
}

async function onToggle(row: any) {
	await serviceAgent.toggleEnabled({ id: row.id, enabled: !row.enabled });
	ElMessage.success(t('agent.profile.toggleSuccess'));
	Crud.value?.refresh();
}
</script>

<style lang="scss" scoped>
.debug-panel {
	display: flex;
	flex-direction: column;
	height: 100%;
	padding: 12px;
	box-sizing: border-box;
}

.debug-messages {
	flex: 1;
	overflow-y: auto;

	.debug-empty {
		color: var(--el-text-color-secondary);
		text-align: center;
		margin-top: 40px;
		font-size: 13px;
	}

	.live-tool {
		display: flex;
		align-items: center;
		gap: 6px;
		color: var(--el-color-primary);
		font-size: 13px;
		margin: 8px 0;
	}

	.streaming {
		background-color: var(--el-fill-color-light);
		padding: 8px 12px;
		border-radius: 8px;
		white-space: pre-wrap;
		margin: 8px 0;
	}
}

.debug-input {
	border-top: 1px solid var(--el-border-color-lighter);
	padding-top: 8px;
	margin-top: 8px;

	.debug-actions {
		display: flex;
		justify-content: flex-end;
		margin-top: 6px;
	}
}

.hash-text {
	font-family: monospace;
	font-size: 12px;
}
</style>
