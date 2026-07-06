<template>
	<div class="session-page">
		<el-card shadow="never">
			<template #header>
				<div class="session-page__header">
					<span>{{ t('设备管理') }}</span>
					<el-button :loading="loading" size="small" @click="refresh">{{ t('刷新') }}</el-button>
				</div>
			</template>

			<el-text type="info" class="session-page__tip">
				{{ t('以下是您的账号当前登录的设备/会话，如发现可疑会话请立即踢出。踢出后该设备将立即下线。') }}
			</el-text>

			<el-table v-loading="loading" :data="list" style="width: 100%; margin-top: 12px">
				<el-table-column :label="t('设备')">
					<template #default="{ row }">
						<span>{{ getClientText(row) }}</span>
					</template>
				</el-table-column>
				<el-table-column :label="t('IP')" prop="ip" width="150">
					<template #default="{ row }">{{ row.ip || '-' }}</template>
				</el-table-column>
				<el-table-column :label="t('登录时间')" width="170">
					<template #default="{ row }">{{ formatTime(row.createdAt) }}</template>
				</el-table-column>
				<el-table-column :label="t('最后活跃')" width="170">
					<template #default="{ row }">{{ formatTime(row.lastActiveAt) }}</template>
				</el-table-column>
				<el-table-column :label="t('状态')" width="110">
					<template #default="{ row }">
						<el-tag v-if="row.current" type="success">{{ t('当前设备') }}</el-tag>
					</template>
				</el-table-column>
				<el-table-column :label="t('操作')" width="100" fixed="right">
					<template #default="{ row }">
						<el-button
							v-if="!row.current"
							type="danger"
							text
							:loading="revokingSid === row.sid"
							@click="onRevoke(row)"
						>
							{{ t('踢出') }}
						</el-button>
					</template>
				</el-table-column>
			</el-table>
		</el-card>
	</div>
</template>

<script lang="ts" setup>
defineOptions({
	name: 'my-session'
});

import { onMounted, ref } from 'vue';
import { useCool } from '/@/cool';
import { useI18n } from 'vue-i18n';
import { ElMessage, ElMessageBox } from 'element-plus';

const { service } = useCool();
const { t } = useI18n();

// eps.d.ts 在 dev server 启动时由后端 EPS 自动生成；新增的 base/session 控制器类型
// 尚未写入快照，这里用 as any 绕过类型检查，运行时由 EPS 正常注入 service.base.session。
const sessionService = (service.base as any).session;

const list = ref<any[]>([]);
const loading = ref(false);
const revokingSid = ref('');

function getOs(userAgent?: string) {
	const ua = (userAgent || '').toLowerCase();
	if (!ua) return t('未知系统');
	if (ua.includes('windows')) return 'Windows';
	if (ua.includes('mac os')) return 'macOS';
	if (ua.includes('iphone') || ua.includes('ipad') || ua.includes('ios')) return 'iOS';
	if (ua.includes('android')) return 'Android';
	if (ua.includes('linux')) return 'Linux';
	return t('未知系统');
}

function getBrowser(userAgent?: string) {
	const ua = userAgent || '';
	if (!ua) return t('未知浏览器');
	const rules = [
		{ name: 'Edge', regex: /Edg\/([\d.]+)/i },
		{ name: 'Chrome', regex: /Chrome\/([\d.]+)/i },
		{ name: 'Firefox', regex: /Firefox\/([\d.]+)/i },
		{ name: 'Safari', regex: /Version\/([\d.]+).*Safari/i }
	];
	for (const item of rules) {
		const match = ua.match(item.regex);
		if (match) return `${item.name} ${match[1]}`;
	}
	return t('未知浏览器');
}

function getClientText(row: any) {
	return `${getOs(row.userAgent)} / ${getBrowser(row.userAgent)}`;
}

function formatTime(ts?: number) {
	if (!ts) return '-';
	const d = new Date(ts * 1000);
	const pad = (n: number) => String(n).padStart(2, '0');
	return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}`;
}

async function refresh() {
	loading.value = true;
	try {
		const res = await sessionService.list();
		list.value = res?.list || [];
	} catch {
		list.value = [];
	} finally {
		loading.value = false;
	}
}

async function onRevoke(row: any) {
	try {
		await ElMessageBox.confirm(t('确定踢出该设备吗？该设备将立即下线。'), t('提示'), {
			type: 'warning'
		});
	} catch {
		return;
	}
	revokingSid.value = row.sid;
	try {
		await sessionService.revoke({ sid: row.sid });
		ElMessage.success(t('已踢出'));
		await refresh();
	} finally {
		revokingSid.value = '';
	}
}

onMounted(() => {
	refresh();
});
</script>

<style lang="scss" scoped>
.session-page {
	&__header {
		display: flex;
		align-items: center;
		justify-content: space-between;
	}

	&__tip {
		display: block;
		line-height: 1.6;
	}
}
</style>
