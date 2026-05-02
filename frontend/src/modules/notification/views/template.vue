<template>
	<cl-crud ref="Crud">
		<cl-row>
			<cl-refresh-btn />
			<cl-add-btn />
			<cl-multi-delete-btn />
			<el-button @click="openPreview">{{ $t('模板预览') }}</el-button>
			<cl-flex1 />
			<cl-search-key :placeholder="$t('搜索编码、名称')" />
		</cl-row>

		<cl-row>
			<cl-table ref="Table" />
		</cl-row>

		<cl-row>
			<cl-flex1 />
			<cl-pagination />
		</cl-row>

		<cl-upsert ref="Upsert" />
	</cl-crud>

	<el-drawer v-model="preview.visible" :title="$t('模板预览')" size="420px">
		<el-alert
			:title="$t('常用变量')"
			description="taskName, taskId, status, consumeTime, detail, executedAt"
			type="info"
			:closable="false"
			class="mb"
		/>
		<el-form label-position="top">
			<el-form-item :label="$t('模板编码')">
				<el-input v-model="preview.code" />
			</el-form-item>
			<el-form-item :label="$t('上下文 JSON')">
				<el-input v-model="preview.context" type="textarea" :rows="8" />
			</el-form-item>
			<el-button type="primary" @click="doPreview">{{ $t('预览') }}</el-button>
		</el-form>
		<el-descriptions v-if="preview.result" :column="1" border class="result">
			<el-descriptions-item :label="$t('标题')">{{ preview.result.title }}</el-descriptions-item>
			<el-descriptions-item :label="$t('内容')">{{ preview.result.content }}</el-descriptions-item>
			<el-descriptions-item :label="$t('级别')">{{ preview.result.level }}</el-descriptions-item>
			<el-descriptions-item :label="$t('链接')">{{ preview.result.linkUrl || '-' }}</el-descriptions-item>
		</el-descriptions>
	</el-drawer>
</template>

<script lang="ts" setup>
defineOptions({
	name: 'notification-template'
});

import { useCrud, useTable, useUpsert } from '@cool-vue/crud';
import { ElMessage } from 'element-plus';
import { reactive } from 'vue';
import { useCool } from '/@/cool';
import { useI18n } from 'vue-i18n';

const { service } = useCool();
const { t } = useI18n();
const preview = reactive({
	visible: false,
	code: '',
	context: '{\\n  "taskName": "示例任务",\\n  "taskId": 1,\\n  "status": "成功",\\n  "consumeTime": 1200,\\n  "detail": "执行完成",\\n  "executedAt": "2026-05-02T00:00:00"\\n}',
	result: null as any
});

const Upsert = useUpsert({
	dialog: { width: '760px' },
	props: { labelWidth: '120px' },
	items: [
		{ label: t('编码'), prop: 'code', required: true, component: { name: 'el-input' } },
		{ label: t('名称'), prop: 'name', required: true, component: { name: 'el-input' } },
		{ label: t('标题模板'), prop: 'titleTemplate', required: true, component: { name: 'el-input' } },
		{
			label: t('内容模板'),
			prop: 'contentTemplate',
			required: true,
			component: { name: 'el-input', props: { type: 'textarea', rows: 5 } }
		},
		{ label: t('默认级别'), prop: 'defaultLevel', value: 'info', component: { name: 'el-input' } },
		{ label: t('默认链接'), prop: 'defaultLinkUrl', component: { name: 'el-input' } },
		{ label: t('启用'), prop: 'isActive', value: true, component: { name: 'el-switch' } }
	]
});

const Table = useTable({
	columns: [
		{ type: 'selection' },
		{ label: t('编码'), prop: 'code', minWidth: 180 },
		{ label: t('名称'), prop: 'name', minWidth: 160 },
		{ label: t('默认级别'), prop: 'defaultLevel', width: 120 },
		{ label: t('启用'), prop: 'isActive', width: 100 },
		{ label: t('创建时间'), prop: 'createTime', sortable: 'desc', minWidth: 170 },
		{ type: 'op', buttons: ['edit', 'delete'] }
	]
});

useCrud(
	{
		service: service.notification.template
	},
	app => {
		app.refresh();
	}
);

function openPreview() {
	preview.visible = true;
	preview.result = null;
}

async function doPreview() {
	try {
		preview.result = await service.notification.template.preview({
			code: preview.code,
			context: JSON.parse(preview.context || '{}')
		});
	} catch (err: any) {
		ElMessage.error(err.message || t('预览失败'));
	}
}
</script>

<style lang="scss" scoped>
.mb {
	margin-bottom: 14px;
}

.result {
	margin-top: 16px;
}
</style>
