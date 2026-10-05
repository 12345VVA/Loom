<template>
	<!--
		工作流执行日志抽屉（全面优化版）：
		- 统计指标看板（步骤数、成功/失败、总耗时）
		- 模糊搜索 & 状态筛选 & 快捷展开/折叠/仅看错误
		- 全屏/还原自由切换
		- 步骤卡片头部元数据增强（节点图标、中文类型、序号、ID复制、耗时智能标记、状态胶囊）
		- Tabs 分栏呈现：执行输出、上游输入、图片产物画廊、智能内容预览、错误详情
		- 语法着色高亮 JSON 视图，带行号、复制与缩放
	-->
	<el-drawer
		:model-value="visible"
		:size="currentDrawerSize"
		:with-header="false"
		destroy-on-close
		class="workflow-log-drawer"
		@update:model-value="(v: boolean) => emit('update:visible', v)"
		@close="emit('close')"
	>
		<div class="log-drawer-container" v-loading="loading">
			<!-- 自定义抽屉头部 -->
			<div class="log-drawer-header">
				<div class="drawer-title-group">
					<div class="title-icon">
						<workflow-icon name="log" :size="18" />
					</div>
					<h3 class="drawer-title">{{ title || $t('工作流步骤执行日志') }}</h3>
					<!-- 运行类型徽标：非生产实例（试运行/评估）显示，生产不占视觉（对齐 IA 规范） -->
					<run-type-tag v-if="runType && runType !== 'production'" :type="runType" />
					<el-tag
						v-if="status !== undefined"
						:type="statusTagType"
						effect="dark"
						size="small"
					>
						{{ statusLabel }}
					</el-tag>
				</div>
				<div class="drawer-header-actions">
					<el-tooltip
						:content="isFullscreen ? $t('退出全屏') : $t('全屏查看')"
						placement="bottom"
					>
						<el-button circle size="small" @click="isFullscreen = !isFullscreen">
							<workflow-icon
								:name="isFullscreen ? 'fullscreen_exit' : 'fullscreen'"
								:size="14"
							/>
						</el-button>
					</el-tooltip>
					<el-button circle size="small" @click="emit('update:visible', false)">
						<workflow-icon name="close" :size="14" />
					</el-button>
				</div>
			</div>

			<!-- Runtime 全景指标看板 -->
			<div v-if="items.length > 0" class="log-metrics-bar">
				<div class="metric-item">
					<span class="metric-label">{{ $t('步骤总数') }}</span>
					<strong class="metric-value">{{ items.length }}</strong>
				</div>
				<div class="metric-divider" />
				<div class="metric-item">
					<span class="metric-label">{{ $t('大模型调用') }}</span>
					<strong class="metric-value llm-count">
						<workflow-icon name="llm" :size="14" class="icon" />
						{{ llmCount }} {{ $t('次') }}
					</strong>
				</div>
				<template v-if="toolCount > 0">
					<div class="metric-divider" />
					<div class="metric-item">
						<span class="metric-label">{{ $t('工具调用') }}</span>
						<strong class="metric-value tool-count">
							<workflow-icon name="tool_executor" :size="14" class="icon" />
							{{ toolCount }} {{ $t('次') }}
						</strong>
					</div>
				</template>
				<template v-if="allWorkflowImages.length > 0">
					<div class="metric-divider" />
					<div class="metric-item">
						<span class="metric-label">{{ $t('图片产物') }}</span>
						<strong class="metric-value media-count">
							<workflow-icon name="images" :size="14" class="icon" />
							{{ allWorkflowImages.length }} {{ $t('张') }}
						</strong>
					</div>
				</template>
				<div class="metric-divider" />
				<div class="metric-item">
					<span class="metric-label">{{ $t('总耗时') }}</span>
					<strong class="metric-value latency">
						<workflow-icon name="timer" :size="14" class="icon" />
						{{ formatLatency(totalLatencyMs) }}
					</strong>
				</div>
				<div class="metric-divider" />
				<div class="metric-item">
					<span class="metric-label">{{ $t('执行状态') }}</span>
					<strong class="metric-value" :class="failCount > 0 ? 'danger' : 'success'">
						{{ failCount > 0 ? `${failCount} ${$t('失败')}` : $t('成功') }}
					</strong>
				</div>

				<!-- 右侧操作栏 -->
				<div class="metrics-right-action">
					<el-button
						v-if="allWorkflowImages.length > 0"
						type="success"
						size="small"
						:loading="downloadingAllZip"
						@click="handleDownloadAllImages"
					>
						<template #icon>
							<workflow-icon name="download" :size="14" />
						</template>
						{{
							downloadingAllZip
								? `${$t('打包中')} ${downloadAllProgressText}`
								: `${$t('打包下载全部图片')} (${allWorkflowImages.length})`
						}}
					</el-button>
					<el-tooltip :content="$t('复制执行摘要')" placement="bottom">
						<el-button size="small" @click="handleCopyRunSummary">
							<template #icon>
								<workflow-icon name="copy" :size="14" />
							</template>
							{{ $t('复制执行摘要') }}
						</el-button>
					</el-tooltip>
				</div>
			</div>

			<!-- 操作工具栏：搜索、筛选、展开控制 -->
			<div v-if="items.length > 0" class="log-toolbar">
				<div class="toolbar-left">
					<el-input
						v-model="searchKeyword"
						size="small"
						:placeholder="$t('搜索节点名称、ID或类型')"
						clearable
						class="search-input"
					>
						<template #prefix>
							<workflow-icon name="search" :size="13" />
						</template>
					</el-input>
					<el-radio-group v-model="filterStatus" size="small" class="status-filter">
						<el-radio-button label="all">{{ $t('全部状态') }}</el-radio-button>
						<el-radio-button label="success">{{ $t('仅看成功') }}</el-radio-button>
						<el-radio-button label="error">{{ $t('仅看失败') }}</el-radio-button>
						<el-radio-button v-if="allWorkflowImages.length > 0" label="media">
							{{ $t('仅看产物') }} ({{ allWorkflowImages.length }})
						</el-radio-button>
					</el-radio-group>
				</div>
				<div class="toolbar-right">
					<el-button-group size="small">
						<el-button @click="handleExpandAll">{{ $t('展开全部') }}</el-button>
						<el-button @click="handleCollapseAll">{{ $t('折叠全部') }}</el-button>
						<el-button
							v-if="failCount > 0"
							type="danger"
							plain
							@click="handleExpandErrorsOnly"
						>
							{{ $t('仅展开失败') }}
						</el-button>
					</el-button-group>
				</div>
			</div>

			<!-- 步骤时间轴主列表 -->
			<div class="log-timeline-wrap">
				<el-timeline v-if="filteredItems.length > 0">
					<el-timeline-item
						v-for="(item, index) in filteredItems"
						:key="item.id || index"
						:type="getTimelineType(item.status)"
						:hollow="item.status === 'running'"
						class="step-timeline-item"
					>
						<!-- 自定义节点卡片 -->
						<div
							class="step-card"
							:class="{
								'is-expanded': item.isExpanded,
								'is-error': item.status === 'error' || item.status === 'failed',
								'is-running': item.status === 'running'
							}"
						>
							<!-- 卡片头部 (可点击展开折叠) -->
							<div class="step-card__header" @click="toggleExpand(item)">
								<div class="header-main">
									<span
										class="expand-arrow"
										:class="{ 'is-active': item.isExpanded }"
									>
										<workflow-icon name="arrow_right" :size="12" />
									</span>

									<span class="step-badge">#{{ getStepIndex(item, index) }}</span>

									<!-- 节点类型 SVG 图标徽标 -->
									<div
										class="node-icon-box"
										:style="{
											color: getNodeMeta(item.nodeType).color,
											backgroundColor: getNodeMeta(item.nodeType).bg
										}"
									>
										<workflow-icon
											:name="getNodeMeta(item.nodeType).icon"
											:size="16"
										/>
									</div>

									<div class="node-title-group">
										<span class="node-name" :title="item.nodeName">{{
											item.nodeName
										}}</span>
										<el-tooltip
											v-if="item.nodeId"
											:content="$t('点击复制节点ID')"
											placement="top"
										>
											<span
												class="node-id-capsule"
												@click.stop="copyNodeId(item.nodeId)"
											>
												{{ item.nodeId }}
											</span>
										</el-tooltip>
									</div>
								</div>

								<div class="header-meta">
									<!-- 包含图片产物时突出显示图片标签 -->
									<el-tag
										v-if="hasDetectedImages(item)"
										size="small"
										type="success"
										effect="plain"
										round
										class="step-image-badge"
									>
										<workflow-icon name="images" :size="13" class="mr-[2px]" />
										{{ getImageCount(item) }} {{ $t('张') }}
									</el-tag>

									<!-- 节点类型标签 -->
									<el-tag
										size="small"
										:type="getNodeMeta(item.nodeType).tagType"
										effect="light"
										class="node-type-tag"
									>
										{{ getNodeMeta(item.nodeType).label }}
									</el-tag>

									<!-- 耗时 Badge -->
									<el-tag
										v-if="item.latencyMs !== undefined"
										size="small"
										round
										:type="getLatencyTagType(item.latencyMs)"
										class="latency-tag"
									>
										<workflow-icon name="timer" :size="13" class="mr-[2px]" />
										{{ formatLatency(item.latencyMs) }}
									</el-tag>

									<!-- 状态徽章 -->
									<el-tag
										size="small"
										:type="getStatusTagType(item.status)"
										effect="dark"
										class="status-tag"
									>
										{{ getStatusLabel(item.status) }}
									</el-tag>

									<!-- 执行时间（简短展示 + 悬停完整日期） -->
									<el-tooltip
										:content="formatFullTime(item.createTime)"
										placement="top"
									>
										<span class="timestamp">{{
											formatShortTime(item.createTime)
										}}</span>
									</el-tooltip>
								</div>
							</div>

							<!-- 卡片展开详情内容（业务结果优先呈现） -->
							<div v-show="item.isExpanded" class="step-card__body">
								<el-tabs
									v-model="activeTabs[item.id || index]"
									class="payload-tabs"
								>
									<!-- 1. 图片画廊 (Gallery) - 优先展现业务交付物 -->
									<el-tab-pane v-if="hasDetectedImages(item)" :name="'gallery'">
										<template #label>
											<span class="tab-label">
												<workflow-icon name="gallery" :size="15" />
												{{ $t('产物画廊') }}
												<el-badge
													:value="getImageCount(item)"
													type="success"
													class="tab-badge"
												/>
											</span>
										</template>
										<div class="tab-pane-content">
											<log-media-gallery
												:list="extractNodeImages(item)"
												:data="item.outputData || item.inputData"
												:step-name="item.nodeName"
											/>
										</div>
									</el-tab-pane>

									<!-- 2. 内容阅读模式 (Content) - 优先展现文案/故事/策划 -->
									<el-tab-pane
										v-if="hasStoryOrCopyContent(item)"
										:name="'preview'"
									>
										<template #label>
											<span class="tab-label">
												<workflow-icon name="preview" :size="15" />
												{{ $t('内容预览') }}
											</span>
										</template>
										<div class="tab-pane-content">
											<log-content-preview :data="item.outputData" />
										</div>
									</el-tab-pane>

									<!-- 3. 执行输出 (Output) - 限高收敛，防撑爆抽屉 -->
									<el-tab-pane :name="'output'">
										<template #label>
											<span class="tab-label">
												<workflow-icon name="output" :size="15" />
												{{ $t('执行输出') }}
											</span>
										</template>
										<div class="tab-pane-content">
											<log-json-viewer
												:value="item.outputData"
												:max-height="220"
												:empty-text="$t('无输出数据')"
											/>
										</div>
									</el-tab-pane>

									<!-- 4. 上游输入 (Input) - 限高收敛 -->
									<el-tab-pane :name="'input'">
										<template #label>
											<span class="tab-label">
												<workflow-icon name="input" :size="15" />
												{{ $t('上游输入') }}
											</span>
										</template>
										<div class="tab-pane-content">
											<log-json-viewer
												:value="item.inputData"
												:max-height="220"
												:empty-text="$t('无输入数据')"
											/>
										</div>
									</el-tab-pane>

									<!-- 5. 错误详情与异常诊断 (Error) - 仅在发生错误时显示 -->
									<el-tab-pane
										v-if="
											item.status === 'error' ||
											item.status === 'failed' ||
											item.errorMessage
										"
										:name="'error'"
									>
										<template #label>
											<span class="tab-label text-danger">
												<workflow-icon name="error" :size="15" />
												{{ $t('异常诊断') }}
											</span>
										</template>
										<div class="tab-pane-content error-pane">
											<div class="error-alert">
												<div class="error-alert-header">
													<div class="error-title-wrap">
														<strong>{{ $t('执行异常') }}</strong>
														<el-tag
															size="small"
															type="danger"
															effect="plain"
														>
															{{
																inferErrorCategory(
																	item.errorMessage || ''
																)
															}}
														</el-tag>
													</div>
													<el-button
														size="small"
														type="danger"
														link
														@click="
															copyErrorMessage(
																item.errorMessage || ''
															)
														"
													>
														<template #icon>
															<workflow-icon name="copy" :size="13" />
														</template>
														{{ $t('复制文本') }}
													</el-button>
												</div>
												<pre class="error-pre">{{
													item.errorMessage || $t('未知错误')
												}}</pre>

												<!-- 异常发生时的上游输入快照 -->
												<div
													v-if="item.inputData"
													class="error-snapshot-box"
												>
													<div class="snapshot-header">
														<span class="snapshot-label">
															<workflow-icon
																name="input"
																:size="13"
															/>
															{{ $t('上游输入快照') }}
														</span>
													</div>
													<log-json-viewer
														:value="item.inputData"
														:max-height="160"
														:show-header="false"
													/>
												</div>
											</div>
										</div>
									</el-tab-pane>
								</el-tabs>
							</div>
						</div>
					</el-timeline-item>
				</el-timeline>

				<!-- 空状态提示 -->
				<el-empty
					v-else
					:description="
						searchKeyword
							? $t('暂无匹配的步骤记录')
							: emptyText || $t('暂无节点执行步骤记录')
					"
					:image-size="100"
				/>
			</div>
		</div>
	</el-drawer>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue';
import WorkflowIcon from './workflow-icon.vue';
import RunTypeTag from './run-type-tag.vue';
import { copyToClipboard, type WorkflowLogItem } from '../utils';
import { useI18n } from 'vue-i18n';
import LogJsonViewer from './log-json-viewer.vue';
import LogMediaGallery from './log-media-gallery.vue';
import LogContentPreview from './log-content-preview.vue';
import { useLogImages } from '../composables/use-log-images';
import { useLogFilter } from '../composables/use-log-filter';
import { useLogExpand } from '../composables/use-log-expand';
import { useLogStats } from '../composables/use-log-stats';
import {
	createNodeMetaMap,
	formatLatency,
	formatShortTime,
	formatFullTime,
	getLatencyTagType,
	getStatusTagType,
	getTimelineType,
	hasStoryOrCopyContent,
	inferErrorCategory as inferErrorCategoryRaw
} from '../utils/log-format';

defineOptions({ name: 'workflow-log-drawer' });

const props = withDefaults(
	defineProps<{
		visible: boolean;
		items: WorkflowLogItem[];
		title?: string;
		size?: string;
		loading?: boolean;
		emptyText?: string;
		/** 提供则显示顶部状态 tag（editor 测试运行用） */
		status?: string;
		/** 实例运行类型（production|trial|eval）：非 production 时头部显示徽标 */
		runType?: string;
		/** 时间格式：editor 测试日志用 HH:mm:ss，instance 步骤日志用完整日期 */
		timeFormat?: string;
	}>(),
	{
		title: '',
		size: '820px',
		loading: false,
		emptyText: '',
		runType: 'production',
		timeFormat: 'HH:mm:ss'
	}
);

const emit = defineEmits<{
	(e: 'update:visible', v: boolean): void;
	(e: 'close'): void;
	(e: 'expand-all'): void;
	(e: 'collapse-all'): void;
}>();

const { t } = useI18n();

const isFullscreen = ref(false);

// 抽屉宽度
const currentDrawerSize = computed(() => {
	if (isFullscreen.value) return '100vw';
	return props.size || '820px';
});

// --- 图片提取与打包下载（composable） ---
const {
	downloadingAllZip,
	downloadAllProgressText,
	extractNodeImages,
	hasDetectedImages,
	getImageCount,
	allWorkflowImages,
	handleDownloadAllImages
} = useLogImages({ items: computed(() => props.items), t });

// --- 筛选（composable） ---
const { searchKeyword, filterStatus, filteredItems } = useLogFilter({
	items: computed(() => props.items),
	hasDetectedImages
});

// --- 展开/Tab 态（composable） ---
function getInitialActiveTab(item: WorkflowLogItem): string {
	if (item.status === 'error' || item.status === 'failed' || item.errorMessage) {
		return 'error';
	}
	if (hasDetectedImages(item)) {
		return 'gallery';
	}
	if (hasStoryOrCopyContent(item)) {
		return 'preview';
	}
	return 'output';
}

const { activeTabs, toggleExpand, handleExpandAll, handleCollapseAll, handleExpandErrorsOnly } =
	useLogExpand({
		items: computed(() => props.items),
		getInitialActiveTab,
		onExpandAll: () => emit('expand-all'),
		onCollapseAll: () => emit('collapse-all')
	});

// --- 格式化与状态映射（utils 纯函数，t 注入） ---
const { getNodeMeta } = createNodeMetaMap(t);

/** 保持 template 原签名：t 由组件层注入 */
function getStatusLabel(status?: string): string {
	if (status === 'success') return t('成功');
	if (status === 'error' || status === 'failed') return t('失败');
	if (status === 'running') return t('运行中');
	return status || '-';
}

/** 保持 template 原签名：t 由组件层注入 */
function inferErrorCategory(msg: string): string {
	return inferErrorCategoryRaw(msg, t);
}

// 统计指标 / 运行状态映射 / 执行摘要（composable，见 use-log-stats.ts）
const {
	failCount,
	totalLatencyMs,
	llmCount,
	toolCount,
	statusTagType,
	statusLabel,
	buildSummaryText
} = useLogStats({
	items: computed(() => props.items),
	status: computed(() => props.status),
	title: computed(() => props.title),
	imageCount: computed(() => allWorkflowImages.value.length),
	t
});

function handleCopyRunSummary() {
	copyToClipboard(buildSummaryText(), t('执行摘要已复制'), t('复制失败'));
}

function getStepIndex(item: WorkflowLogItem, fallbackIndex: number): number {
	const realIndex = props.items.indexOf(item);
	return realIndex !== -1 ? realIndex + 1 : fallbackIndex + 1;
}

function copyNodeId(nodeId: string) {
	copyToClipboard(nodeId, t('节点ID已复制'), t('复制失败'));
}

function copyErrorMessage(msg: string) {
	copyToClipboard(msg, t('复制成功'), t('复制失败'));
}
</script>


<style lang="scss" scoped>
.workflow-log-drawer {
	:deep(.el-drawer__body) {
		padding: 0;
		display: flex;
		flex-direction: column;
		height: 100%;
		overflow: hidden;
	}
}

.log-drawer-container {
	display: flex;
	flex-direction: column;
	height: 100%;
	background: var(--el-bg-color);
}

.log-drawer-header {
	display: flex;
	align-items: center;
	justify-content: space-between;
	padding: 16px 20px;
	border-bottom: 1px solid var(--el-border-color-lighter);
	background: var(--el-bg-color-overlay);

	.drawer-title-group {
		display: flex;
		align-items: center;
		gap: 10px;

		.title-icon {
			display: flex;
			align-items: center;
			justify-content: center;
			width: 32px;
			height: 32px;
			border-radius: 8px;
			background: var(--el-color-primary-light-9);
			color: var(--el-color-primary);
			font-size: 18px;
		}

		.drawer-title {
			margin: 0;
			font-size: 16px;
			font-weight: 600;
			color: var(--el-text-color-primary);
		}
	}

	.drawer-header-actions {
		display: flex;
		align-items: center;
		gap: 8px;
	}
}

.log-metrics-bar {
	display: flex;
	align-items: center;
	padding: 12px 20px;
	background: var(--el-fill-color-lighter);
	border-bottom: 1px solid var(--el-border-color-lighter);
	gap: 16px;

	.metric-item {
		display: flex;
		flex-direction: column;
		gap: 2px;

		.metric-label {
			font-size: 11px;
			color: var(--el-text-color-secondary);
		}

		.metric-value {
			font-size: 16px;
			font-weight: 600;
			color: var(--el-text-color-primary);
			font-family: ui-monospace, SFMono-Regular, monospace;

			&.success {
				color: var(--el-color-success);
			}

			&.danger {
				color: var(--el-color-danger);
			}

			&.llm-count {
				display: flex;
				align-items: center;
				gap: 4px;
				color: #8b5cf6;

				.icon {
					font-size: 14px;
				}
			}

			&.tool-count {
				display: flex;
				align-items: center;
				gap: 4px;
				color: #0284c7;

				.icon {
					font-size: 14px;
				}
			}

			&.latency {
				display: flex;
				align-items: center;
				gap: 4px;
				color: #0284c7;

				.icon {
					font-size: 14px;
				}
			}

			&.media-count {
				display: flex;
				align-items: center;
				gap: 4px;
				color: #10b981;

				.icon {
					font-size: 14px;
				}
			}
		}
	}

	.metric-divider {
		width: 1px;
		height: 24px;
		background: var(--el-border-color-light);
	}

	.metrics-right-action {
		margin-left: auto;
		display: flex;
		align-items: center;
	}
}

.log-toolbar {
	display: flex;
	align-items: center;
	justify-content: space-between;
	padding: 12px 20px 8px;
	gap: 12px;
	flex-wrap: wrap;

	.toolbar-left {
		display: flex;
		align-items: center;
		gap: 10px;

		.search-input {
			width: 220px;

			:deep(.el-input__wrapper) {
				border-radius: 16px;
			}
		}
	}

	.toolbar-right {
		display: flex;
		align-items: center;
	}
}

.log-timeline-wrap {
	flex: 1;
	overflow-y: auto;
	padding: 16px 20px 24px;

	:deep(.el-timeline) {
		padding-left: 6px;
	}

	.step-timeline-item {
		padding-bottom: 16px;
	}
}

.step-card {
	border: 1px solid var(--el-border-color-lighter);
	border-radius: 10px;
	background: var(--el-bg-color-overlay);
	box-shadow: 0 1px 4px rgba(0, 0, 0, 0.03);
	overflow: hidden;
	transition: all 0.2s ease-in-out;

	&:hover {
		border-color: var(--el-color-primary-light-6);
		box-shadow: 0 3px 10px rgba(0, 0, 0, 0.06);
	}

	&.is-error {
		border-color: var(--el-color-danger-light-5);
		background: var(--el-color-danger-light-9);
	}

	&.is-running {
		border-color: var(--el-color-primary);
	}

	&__header {
		display: flex;
		align-items: center;
		justify-content: space-between;
		padding: 10px 14px;
		cursor: pointer;
		user-select: none;
		background: var(--el-fill-color-blank);
		transition: background-color 0.2s;

		&:hover {
			background: var(--el-fill-color-light);
		}

		.header-main {
			display: flex;
			align-items: center;
			gap: 10px;
			min-width: 0;
			flex: 1;

			.expand-arrow {
				font-size: 14px;
				color: var(--el-text-color-placeholder);
				transition: transform 0.2s;

				&.is-active {
					transform: rotate(90deg);
					color: var(--el-color-primary);
				}
			}

			.step-badge {
				font-size: 11px;
				font-weight: 700;
				color: var(--el-text-color-secondary);
				font-family: monospace;
			}

			.node-icon-box {
				display: flex;
				align-items: center;
				justify-content: center;
				width: 28px;
				height: 28px;
				border-radius: 6px;
				font-size: 15px;
				flex-shrink: 0;
			}

			.node-title-group,
			.node-title-box {
				display: flex;
				align-items: center;
				gap: 8px;
				min-width: 0;

				.node-name {
					font-size: 14px;
					font-weight: 600;
					color: var(--el-text-color-primary);
					overflow: hidden;
					text-overflow: ellipsis;
					white-space: nowrap;
				}

				.node-id-capsule {
					font-size: 11px;
					font-family: ui-monospace, SFMono-Regular, monospace;
					padding: 1px 6px;
					border-radius: 4px;
					background: var(--el-fill-color);
					color: var(--el-text-color-secondary);
					cursor: pointer;
					transition: all 0.2s;

					&:hover {
						background: var(--el-color-primary-light-9);
						color: var(--el-color-primary);
					}
				}
			}
		}

		.header-meta {
			display: flex;
			align-items: center;
			gap: 8px;
			flex-shrink: 0;

			.latency-tag {
				font-family: monospace;
				font-weight: 500;
			}

			.timestamp {
				font-size: 11px;
				color: var(--el-text-color-placeholder);
				margin-left: 4px;
			}
		}
	}

	&__body {
		padding: 0 14px 14px;
		border-top: 1px solid var(--el-border-color-lighter);
		background: var(--el-bg-color-overlay);

		.payload-tabs {
			:deep(.el-tabs__header) {
				margin: 0 0 12px 0;
			}

			:deep(.el-tabs__nav-wrap::after) {
				height: 1px;
			}

			.tab-label {
				display: flex;
				align-items: center;
				gap: 6px;
				font-size: 13px;

				&.text-danger {
					color: var(--el-color-danger);
				}

				.tab-badge {
					:deep(.el-badge__content) {
						font-size: 10px;
						padding: 0 4px;
						height: 16px;
						line-height: 16px;
					}
				}
			}
		}
	}
}

.error-pane {
	.error-alert {
		border: 1px solid var(--el-color-danger-light-5);
		border-radius: 8px;
		background: var(--el-color-danger-light-9);
		padding: 12px;

		.error-alert-header {
			display: flex;
			justify-content: space-between;
			align-items: center;
			margin-bottom: 8px;
			color: var(--el-color-danger);

			.error-title-wrap {
				display: flex;
				align-items: center;
				gap: 8px;
			}
		}

		.error-pre {
			margin: 0;
			padding: 10px;
			background: var(--el-bg-color-overlay);
			border-radius: 4px;
			font-family: monospace;
			font-size: 12px;
			color: var(--el-color-danger);
			white-space: pre-wrap;
			word-break: break-all;
			max-height: 280px;
			overflow-y: auto;
		}

		.error-snapshot-box {
			margin-top: 12px;
			border-top: 1px dashed var(--el-color-danger-light-7);
			padding-top: 8px;

			.snapshot-header {
				margin-bottom: 6px;

				.snapshot-label {
					font-size: 12px;
					font-weight: 500;
					color: var(--el-text-color-secondary);
					display: inline-flex;
					align-items: center;
					gap: 4px;
				}
			}
		}
	}
}
</style>
