<template>
	<cl-crud ref="Crud">
		<cl-row>
			<cl-refresh-btn />
			<!-- 自定义新增按钮：四动作无 update，不用框架 upsert（cl-add-btn 依赖 cl-upsert 代理） -->
			<el-button
				v-permission="service.workflow.memory.permission.add"
				type="primary"
				@click="openAddDialog"
			>
				{{ $t('新增') }}
			</el-button>
			<cl-multi-delete-btn />
			<cl-flex1 />
			<cl-search-key :placeholder="$t('搜索内容、业务身份')" />
		</cl-row>

		<cl-row>
			<!-- 工作流主维度筛选器 + 环境分段 + 来源渠道筛选（§11：source_run_type 一等能力——
				 trial 兜底清理与 test 残留清理依赖此过滤器） -->
			<el-select
				v-model="definitionFilter"
				clearable
				filterable
				:placeholder="$t('按工作流筛选')"
				style="width: 220px; margin-right: 10px"
				@change="onFilterChange"
			>
				<el-option v-for="d in definitions" :key="d.id" :label="d.name" :value="d.id" />
			</el-select>

			<el-radio-group v-model="envFilter" style="margin-right: 10px" @change="onFilterChange">
				<el-radio-button label="production">{{ $t('生产') }}</el-radio-button>
				<el-radio-button label="test">{{ $t('测试') }}</el-radio-button>
				<el-radio-button label="all">{{ $t('全部') }}</el-radio-button>
			</el-radio-group>

			<el-select
				v-model="sourceRunTypeFilter"
				clearable
				:placeholder="$t('来源渠道')"
				style="width: 150px"
				@change="onFilterChange"
			>
				<el-option :label="$t('生产运行')" value="production" />
				<el-option :label="$t('试运行')" value="trial" />
				<el-option :label="$t('单点测试')" value="test_node" />
				<el-option :label="$t('管理页新增')" value="admin" />
			</el-select>
		</cl-row>

		<cl-row>
			<cl-table ref="Table">
				<template #column-definitionName="{ scope }">
					<el-link
						type="primary"
						:underline="false"
						@click="goToEditor(scope.row.definitionId)"
					>
						{{ scope.row.definitionName || `#${scope.row.definitionId}` }}
					</el-link>
				</template>
				<template #column-content="{ scope }">
					<el-tooltip
						v-if="scope.row.credentialHits?.length"
						:content="$t('内容疑似包含凭据模式：') + toCredentialHits(scope.row.credentialHits).join(', ')"
						placement="top"
					>
						<el-icon color="#e6a23c" style="vertical-align: -2px; margin-right: 4px"
							><warning-filled
						/></el-icon>
					</el-tooltip>
					<span>{{ scope.row.content }}</span>
				</template>
				<template #column-sourceInstanceId="{ scope }">
					<el-tooltip
						v-if="scope.row.sourceInstanceId"
						:content="$t('来源运行实例（实例删除后仍保留编号溯源）')"
						placement="top"
					>
						<el-tag size="small" type="info">#{{ scope.row.sourceInstanceId }}</el-tag>
					</el-tooltip>
					<span v-else>-</span>
				</template>
				<template #slot-detail="{ scope }">
					<el-button text type="primary" @click="openDetail(scope.row)">
						{{ $t('详情') }}
					</el-button>
				</template>
				<template #slot-delete="{ scope }">
					<el-button
						v-permission="service.workflow.memory.permission.delete"
						text
						type="danger"
						@click="onDeleteRow(scope.row)"
					>
						{{ $t('删除') }}
					</el-button>
				</template>
			</cl-table>
		</cl-row>

		<cl-row>
			<cl-flex1 />
			<cl-pagination />
		</cl-row>
	</cl-crud>

	<!-- 手工新增弹窗（四动作无 update：修正走删旧+新增或工作流侧同 key 覆盖，§11/§16） -->
	<el-dialog
		v-model="addDialog.visible"
		:title="$t('新增记忆')"
		width="560px"
		destroy-on-close
	>
		<el-form :model="addDialog.form" label-width="120px">
			<el-form-item :label="$t('所属工作流')" required>
				<el-select
					v-model="addDialog.form.definitionId"
					filterable
					:placeholder="$t('选择记忆归属的工作流')"
					style="width: 100%"
				>
					<el-option v-for="d in definitions" :key="d.id" :label="d.name" :value="d.id" />
				</el-select>
			</el-form-item>
			<el-form-item :label="$t('记忆内容')" required>
				<el-input
					v-model="addDialog.form.content"
					type="textarea"
					:rows="5"
					maxlength="4000"
					show-word-limit
					:placeholder="$t('沉淀给后续运行使用的事实/口径/决策，如：客户 X 报价口径 8 折')"
				/>
			</el-form-item>
			<el-form-item :label="$t('业务身份 (key)')">
				<el-input
					v-model="addDialog.form.memoryKey"
					:placeholder="$t('例如: customer:42:quote_policy（同 key 视为同一记忆）')"
				/>
			</el-form-item>
			<el-form-item :label="$t('记忆类型')">
				<el-select v-model="addDialog.form.memoryType" style="width: 100%">
					<el-option label="事实 (fact)" value="fact" />
					<el-option
						:label="$t('偏好口径 (preference)——工作流级口径')"
						value="preference"
					/>
					<el-option :label="$t('决策记录 (decision)')" value="decision" />
					<el-option :label="$t('历史经验 (experience)')" value="experience" />
				</el-select>
			</el-form-item>
			<el-form-item :label="$t('标签')">
				<el-select
					v-model="addDialog.form.tags"
					multiple
					filterable
					allow-create
					default-first-option
					:placeholder="$t('回车添加，用于召回时粗滤')"
					style="width: 100%"
				/>
			</el-form-item>
			<el-form-item :label="$t('向量化 Profile')">
				<el-select
					v-model="addDialog.form.embeddingProfileCode"
					clearable
					filterable
					:placeholder="$t('留空则不生成向量（走关键词召回）')"
					style="width: 100%"
				>
					<el-option
						v-for="p in embeddingProfileList"
						:key="p.code"
						:label="p.name + ' (' + p.code + ')'"
						:value="p.code || ''"
					/>
				</el-select>
				<div class="field-hint">
					{{
						$t(
							'填且生成成功 → 可语义召回；生成失败 → 仅关键词召回；留空 → 不生成向量。手工新增恒为生产环境，溯源标记为「管理页新增」'
						)
					}}
				</div>
			</el-form-item>
		</el-form>
		<template #footer>
			<el-button @click="addDialog.visible = false">{{ $t('取消') }}</el-button>
			<el-button type="primary" :loading="addDialog.loading" @click="submitAdd">
				{{ $t('保存') }}
			</el-button>
		</template>
	</el-dialog>

	<!-- 详情对话框（info 动作） -->
	<el-dialog v-model="detail.visible" :title="$t('记忆详情')" width="640px">
		<el-descriptions v-if="detail.row" :column="2" border>
			<el-descriptions-item :label="$t('工作流')">
				{{ detail.row.definitionName || `#${detail.row.definitionId}` }}
			</el-descriptions-item>
			<el-descriptions-item :label="$t('环境')">
				<el-tag size="small" :type="detail.row.memoryEnv === 'test' ? 'info' : 'success'">
					{{ detail.row.memoryEnv === 'test' ? $t('测试') : $t('生产') }}
				</el-tag>
			</el-descriptions-item>
			<el-descriptions-item :label="$t('业务身份')">
				{{ detail.row.memoryKey || '-' }}
			</el-descriptions-item>
			<el-descriptions-item :label="$t('记忆类型')">
				{{ memoryTypeLabel(detail.row.memoryType) }}
			</el-descriptions-item>
			<el-descriptions-item :label="$t('内容')" :span="2">
				<div style="white-space: pre-wrap; word-break: break-all">{{ detail.row.content }}</div>
			</el-descriptions-item>
			<el-descriptions-item :label="$t('标签')" :span="2">
				{{ parseTags(detail.row.tags).join('、') || '-' }}
			</el-descriptions-item>
			<el-descriptions-item :label="$t('向量状态')" :span="2">
				{{ embeddingStateLabel(detail.row.embeddingSpace) }}
			</el-descriptions-item>
			<el-descriptions-item :label="$t('来源渠道')">
				{{ sourceRunTypeLabel(detail.row.sourceRunType) }}
			</el-descriptions-item>
			<el-descriptions-item :label="$t('来源实例')">
				{{ detail.row.sourceInstanceId ? `#${detail.row.sourceInstanceId}` : '-' }}
				<template v-if="detail.row.sourceNodeId">
					（{{ detail.row.sourceNodeId }}）
				</template>
			</el-descriptions-item>
			<el-descriptions-item :label="$t('创建者 / 最后写入')">
				#{{ detail.row.createdByUserId ?? '-' }} / #{{ detail.row.updatedByUserId ?? '-' }}
			</el-descriptions-item>
			<el-descriptions-item :label="$t('最近命中')">
				{{ detail.row.lastAccessedAt || '-' }}
			</el-descriptions-item>
			<el-descriptions-item :label="$t('写入时间')">
				{{ detail.row.createTime }}
			</el-descriptions-item>
			<el-descriptions-item :label="$t('更新时间')">
				{{ detail.row.updateTime }}
			</el-descriptions-item>
			<el-descriptions-item v-if="detail.row.credentialHits?.length" :span="2">
				<template #label>
					<span style="color: var(--el-color-warning)">{{ $t('凭据警告') }}</span>
				</template>
				{{ toCredentialHits(detail.row.credentialHits).join(', ') }}
			</el-descriptions-item>
		</el-descriptions>
	</el-dialog>
</template>

<script lang="ts" setup>
defineOptions({
	name: 'workflow-memory'
});

import { useCrud, useTable } from '@cool-vue/crud';
import { useCool } from '/@/cool';
import { ref, reactive, computed, onMounted } from 'vue';
import { useI18n } from 'vue-i18n';
import { ElMessage, ElMessageBox } from 'element-plus';
import { WarningFilled } from '@element-plus/icons-vue';

const { service, router } = useCool();
const { t } = useI18n();

// 行类型取 EPS 权威实体（build/cool/eps.d.ts interface memory，含响应期 credentialHits）
type MemoryRow = Eps.memory;

interface DefinitionOption {
	id: number;
	name: string;
}

const definitions = ref<DefinitionOption[]>([]);
const embeddingProfiles = ref<Eps.profile[]>([]);

// --- 筛选（§11：工作流主维度 + 环境分段 + source_run_type 一等筛选）---
const definitionFilter = ref<number | undefined>(undefined);
const envFilter = ref<'production' | 'test' | 'all'>('production');
const sourceRunTypeFilter = ref<string | undefined>(undefined);

function onFilterChange() {
	Crud.value?.refresh({
		definitionId: definitionFilter.value,
		memoryEnv: envFilter.value === 'all' ? undefined : envFilter.value,
		sourceRunType: sourceRunTypeFilter.value,
		page: 1
	});
}

function goToEditor(definitionId?: number) {
	if (!definitionId) return;
	router.push({ path: '/workflow/editor', query: { id: definitionId } });
}

// --- 展示辅助 ---
const MEMORY_TYPE_LABELS: Record<string, string> = {
	fact: '事实',
	preference: '偏好口径',
	decision: '决策',
	experience: '经验'
};

function memoryTypeLabel(v?: string) {
	return v ? t(MEMORY_TYPE_LABELS[v] || v) : '-';
}

const SOURCE_RUN_TYPE_LABELS: Record<string, string> = {
	production: '生产运行',
	trial: '试运行',
	test_node: '单点测试',
	admin: '管理页新增'
};

function sourceRunTypeLabel(v?: string) {
	return v ? t(SOURCE_RUN_TYPE_LABELS[v] || v) : '-';
}

// embedding 三态（§4.5）：NULL=未配置 / 裸 code（无维度段）=生成失败 / model:dimension=ready
function embeddingStateLabel(space?: string) {
	if (!space) return t('未配置向量（关键词召回）');
	if (space.includes(':')) return t('向量就绪') + ` (${space})`;
	return t('向量生成失败，仅关键词召回') + ` (${space})`;
}

function parseTags(tags?: string): string[] {
	try {
		const arr = JSON.parse(tags || '[]');
		return Array.isArray(arr) ? arr : [];
	} catch {
		return [];
	}
}

// Eps.memory 的 credentialHits 被 EPS 实体推断为 string（响应期计算字段的推断局限），
// 实际运行时为 string[]——归一为数组
function toCredentialHits(v: unknown): string[] {
	if (Array.isArray(v)) return v as string[];
	return v ? [String(v)] : [];
}

// --- 手工新增（显式选工作流；恒 production env + admin 溯源，由后端保证）---
const addDialog = reactive({
	visible: false,
	loading: false,
	form: {
		definitionId: undefined as number | undefined,
		content: '',
		memoryKey: '',
		memoryType: 'fact',
		tags: [] as string[],
		embeddingProfileCode: ''
	}
});

function openAddDialog() {
	addDialog.form = {
		definitionId: definitionFilter.value,
		content: '',
		memoryKey: '',
		memoryType: 'fact',
		tags: [],
		embeddingProfileCode: ''
	};
	addDialog.visible = true;
}

async function submitAdd() {
	if (!addDialog.form.definitionId) {
		ElMessage.warning(t('请选择所属工作流'));
		return;
	}
	if (!addDialog.form.content.trim()) {
		ElMessage.warning(t('请填写记忆内容'));
		return;
	}
	addDialog.loading = true;
	try {
		const res = await service.workflow.memory.add({
			definitionId: addDialog.form.definitionId,
			content: addDialog.form.content,
			memoryKey: addDialog.form.memoryKey || undefined,
			memoryType: addDialog.form.memoryType,
			tags: addDialog.form.tags,
			embeddingProfileCode: addDialog.form.embeddingProfileCode || undefined
		});
		if (res?.credentialHits?.length) {
			ElMessage.warning(t('已保存，但内容疑似包含凭据模式，建议尽快处理：') + res.credentialHits.join(', '));
		} else {
			ElMessage.success(t('记忆已保存'));
		}
		addDialog.visible = false;
		Crud.value?.refresh();
	} catch (e) {
		ElMessage.error(t('保存失败：') + (e instanceof Error ? e.message : String(e)));
	} finally {
		addDialog.loading = false;
	}
}

// --- 详情 ---
const detail = reactive({
	visible: false,
	row: null as MemoryRow | null
});

async function openDetail(row: MemoryRow) {
	try {
		const res = await service.workflow.memory.info({ id: row.id! });
		detail.row = res;
		detail.visible = true;
	} catch (e) {
		ElMessage.error(t('获取详情失败：') + (e instanceof Error ? e.message : String(e)));
	}
}

// --- 删除（§11 澄清 13：delete 旁提示「修正建议：删旧+新增」）---
function onDeleteRow(row: MemoryRow) {
	ElMessageBox.confirm(
		t(
			'确定删除该条记忆？删除后不再参与召回。如需修正内容，建议删旧后新增，或通过工作流 memory_store 节点配置同 key 模板覆盖。'
		),
		t('删除记忆'),
		{ type: 'warning' }
	)
		.then(async () => {
			try {
				await service.workflow.memory.delete({ ids: [row.id!] });
				ElMessage.success(t('已删除'));
				Crud.value?.refresh();
			} catch (e) {
				ElMessage.error(t('删除失败：') + (e instanceof Error ? e.message : String(e)));
			}
		})
		.catch(() => null);
}

const Table = useTable({
	columns: [
		{ type: 'selection' },
		{
			label: t('ID'),
			prop: 'id',
			width: 70,
			align: 'center',
			formatter: (row: MemoryRow) => `#${row.id}`
		},
		{
			label: t('工作流'),
			prop: 'definitionName',
			minWidth: 150,
			showOverflowTooltip: true
		},
		{
			label: t('环境'),
			prop: 'memoryEnv',
			width: 80,
			align: 'center',
			dict: [
				{ label: t('生产'), value: 'production', type: 'success' },
				{ label: t('测试'), value: 'test', type: 'info' }
			],
			dictColor: true
		},
		{
			label: t('类型'),
			prop: 'memoryType',
			width: 95,
			align: 'center',
			dict: [
				{ label: t('事实'), value: 'fact' },
				{ label: t('偏好口径'), value: 'preference', type: 'warning' },
				{ label: t('决策'), value: 'decision', type: 'success' },
				{ label: t('经验'), value: 'experience', type: 'primary' }
			]
		},
		{
			label: t('业务身份'),
			prop: 'memoryKey',
			minWidth: 160,
			showOverflowTooltip: true,
			formatter: (_row: MemoryRow, _col: unknown, val: string) => val || '-'
		},
		{
			label: t('内容'),
			prop: 'content',
			minWidth: 260,
			showOverflowTooltip: true
		},
		{
			label: t('标签'),
			prop: 'tags',
			minWidth: 120,
			showOverflowTooltip: true,
			formatter: (row: MemoryRow) => parseTags(row.tags).join('、') || '-'
		},
		{
			label: t('来源渠道'),
			prop: 'sourceRunType',
			width: 100,
			align: 'center',
			dict: [
				{ label: t('生产运行'), value: 'production' },
				{ label: t('试运行'), value: 'trial', type: 'warning' },
				{ label: t('单点测试'), value: 'test_node', type: 'info' },
				{ label: t('管理页新增'), value: 'admin', type: 'success' }
			],
			formatter: (_row: MemoryRow, _col: unknown, val: string) => val || '-'
		},
		{
			label: t('来源实例'),
			prop: 'sourceInstanceId',
			width: 90,
			align: 'center'
		},
		{
			label: t('创建/写入者'),
			prop: 'createdByUserId',
			width: 110,
			align: 'center',
			formatter: (row: MemoryRow) => `#${row.createdByUserId ?? '-'} → #${row.updatedByUserId ?? '-'}`
		},
		{
			label: t('最近命中'),
			prop: 'lastAccessedAt',
			minWidth: 165,
			component: { name: 'cl-date-text' }
		},
		{
			label: t('写入时间'),
			prop: 'updateTime',
			sortable: 'desc',
			minWidth: 165,
			component: { name: 'cl-date-text' }
		},
		{
			type: 'op',
			width: 140,
			buttons: ['slot-detail', 'slot-delete']
		}
	]
});

const Crud = useCrud(
	{
		service: service.workflow.memory
	},
	app => {
		// 默认只看生产记忆（crud.params 持久 merge，翻页/搜索自动携带）
		app.refresh({
			memoryEnv: envFilter.value === 'all' ? undefined : envFilter.value
		});
	}
);

const embeddingProfileList = computed(() =>
	embeddingProfiles.value.filter(p => p.modelType === 'embedding')
);

onMounted(async () => {
	try {
		const list = await service.workflow.definition.list({});
		definitions.value = list
			.filter(d => d.id != null)
			.map(d => ({ id: d.id!, name: d.name || `#${d.id}` }));
	} catch (e) {
		ElMessage.error(t('工作流列表加载失败：') + (e instanceof Error ? e.message : String(e)));
	}
	try {
		embeddingProfiles.value = await service.ai.profile.list({});
	} catch {
		// profile 拉取失败不阻断页面（新增时向量化留空即可）
	}
});
</script>

<style lang="scss" scoped>
.field-hint {
	font-size: 11px;
	color: var(--el-text-color-placeholder);
	line-height: 1.4;
	margin-top: 4px;
}
</style>
