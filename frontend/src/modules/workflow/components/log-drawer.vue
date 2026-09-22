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
import { computed, reactive, ref, watch } from 'vue';
import WorkflowIcon from './workflow-icon.vue';
import { copyToClipboard, type WorkflowLogItem } from '../utils';
import { downloadImagesAsZip, type ImageDownloadItem } from '../utils/download';
import { useAssetUrl } from '/$/media/composables/use-asset-url';
import dayjs from 'dayjs';
import { useI18n } from 'vue-i18n';
import { ElMessage } from 'element-plus';
import LogJsonViewer from './log-json-viewer.vue';
import LogMediaGallery from './log-media-gallery.vue';
import LogContentPreview from './log-content-preview.vue';

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
		/** 时间格式：editor 测试日志用 HH:mm:ss，instance 步骤日志用完整日期 */
		timeFormat?: string;
	}>(),
	{
		title: '',
		size: '820px',
		loading: false,
		emptyText: '',
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
const { assetUrl, ensureDownloadToken } = useAssetUrl();

const isFullscreen = ref(false);
const searchKeyword = ref('');
const filterStatus = ref<'all' | 'success' | 'error' | 'media'>('all');
const downloadingAllZip = ref(false);
const downloadAllProgressText = ref('');

function resolveUrl(url: string): string {
	if (!url) return '';
	const s = url.trim();
	if (s.startsWith('data:image/') || s.startsWith('blob:')) {
		return s;
	}
	// 任何包含 /uploads/ 的路径，统一经由 assetUrl 剥离旧 token 并注入当前有效 token
	if (s.includes('/uploads/')) {
		return assetUrl(s);
	}
	if (s.startsWith('http://') || s.startsWith('https://')) {
		return s;
	}
	const normalized = s.startsWith('/') ? s : `/${s}`;
	return assetUrl(normalized);
}

function isLikelyImageUrl(key: string, val: string): boolean {
	if (!val || typeof val !== 'string') return false;
	const s = val.trim();

	// 1. 基础长度限制：一个有效图片路径通常至少为 5 个字符（如 a.png）
	if (s.length < 5 || s.length > 2000) return false;

	// 2. 绝对安全性检查：图片 URL 绝不能包含空格、换行、制表符或中文标点符号
	if (/[\s\n\r\t，。！？“”《》]/.test(s)) {
		return false;
	}

	// 3. 字段名黑名单：提示词、文案、标题、描述、代码等文本字段坚决排除
	const nonImgKeyRegex =
		/(prompt|text|desc|instruction|query|param|title|message|content|article|script|schema|code|token|header|note|point)/i;
	if (nonImgKeyRegex.test(key)) {
		return false;
	}

	// 4. Base64 图片 (以 data:image/ 开头)
	if (s.startsWith('data:image/')) {
		return true;
	}

	// 5. 清除 query 参数和 hash 后的干净路径
	const cleanUrl = s.split('?')[0].split('#')[0];
	const hasImgExt = /\.(png|jpe?g|webp|gif|svg|bmp|tiff|avif|ico)$/i.test(cleanUrl);

	// 6. 本地静态资源目录（/uploads/ 或 /static/，支持前导斜杠或无斜杠）
	const isLocalStaticPath =
		cleanUrl.startsWith('/uploads/') ||
		cleanUrl.startsWith('uploads/') ||
		cleanUrl.includes('/uploads/') ||
		cleanUrl.startsWith('/static/') ||
		cleanUrl.startsWith('static/') ||
		cleanUrl.includes('/static/');

	if (isLocalStaticPath) {
		// 本地上传路径必须带有合法图片扩展名，或带有明确图片属性名
		if (hasImgExt) return true;
		const explicitImgKey = /^(image|image_url|cover|cover_image_url|img|pic|photo|thumbnail)$/i;
		if (explicitImgKey.test(key) && cleanUrl.includes('/')) return true;
	}

	// 7. 远端 Web URL (http:// 或 https://)
	const isHttp = cleanUrl.startsWith('http://') || cleanUrl.startsWith('https://');
	if (isHttp) {
		if (hasImgExt) return true;
		// 动态签名无扩展名图片必须有强图片字段名
		const explicitImgKey =
			/^(image|image_url|cover|cover_image_url|img|pic|photo|thumbnail|artwork)$/i;
		if (explicitImgKey.test(key)) return true;
	}

	// 8. 相对路径（以 / 或 ./ 开头）必须具备图片扩展名
	if ((cleanUrl.startsWith('/') || cleanUrl.startsWith('./')) && hasImgExt) {
		return true;
	}

	return false;
}

/**
 * 从任意载荷数据中深层挖掘图片（支持对象、循环结果数组、纯图片字符串数组、嵌套序列化子 JSON）
 */
function extractRawImagesFromData(data: any, nodeName?: string): ImageDownloadItem[] {
	if (!data) return [];
	let parsed = data;
	if (typeof data === 'string') {
		const trimmed = data.trim();
		if (trimmed.startsWith('{') || trimmed.startsWith('[')) {
			try {
				parsed = JSON.parse(data);
			} catch {
				parsed = null;
			}
		} else {
			parsed = null;
		}
	}

	const list: ImageDownloadItem[] = [];
	const seenUrls = new Set<string>();

	function checkAndAdd(val: string, key: string, parentObj: any) {
		if (isLikelyImageUrl(key, val)) {
			const resolved = resolveUrl(val);
			if (resolved && !seenUrls.has(resolved)) {
				seenUrls.add(resolved);

				let subtitle = '';
				if (parentObj) {
					if (parentObj.story_text) subtitle = parentObj.story_text;
					else if (parentObj.scene_prompt) subtitle = parentObj.scene_prompt;
					else if (parentObj.prompt) subtitle = parentObj.prompt;
					else if (parentObj.paragraph_id) subtitle = `段落 ${parentObj.paragraph_id}`;
					else if (parentObj.page_number) subtitle = `第 ${parentObj.page_number} 页`;
					else if (parentObj.index !== undefined)
						subtitle = `#${Number(parentObj.index) + 1}`;
				}

				let title = key;
				if (key === 'cover_image_url' || key === 'cover') title = t('封面图');
				else if (key === 'image_url' || key === 'image' || key === 'img') title = t('插图');
				else if (parentObj && parentObj.paragraph_id)
					title = `${t('段落')} ${parentObj.paragraph_id}`;

				list.push({
					url: resolved,
					title: title || nodeName || 'image',
					subtitle
				});
			}
		}
	}

	function traverse(obj: any, currentKey = '') {
		if (!obj) return;

		// 核心：支持数组（纯图片字符串数组或对象数组）
		if (Array.isArray(obj)) {
			obj.forEach((item, idx) => {
				const itemKey = currentKey ? `${currentKey}[${idx}]` : `[${idx}]`;
				if (typeof item === 'string') {
					const trimmed = item.trim();
					// 如果数组元素也是序列化 JSON 字符串，尝试深层解析
					if (trimmed.startsWith('{') || trimmed.startsWith('[')) {
						try {
							const sub = JSON.parse(trimmed);
							traverse(sub, itemKey);
							return;
						} catch {
							// 忽略解析失败，继续作为普通字符串匹配
						}
					}
					checkAndAdd(item, itemKey, null);
				} else if (typeof item === 'object' && item !== null) {
					traverse(item, itemKey);
				}
			});
			return;
		}

		if (typeof obj !== 'object') return;

		for (const [k, v] of Object.entries(obj)) {
			const fullKey = currentKey ? `${currentKey}.${k}` : k;
			if (typeof v === 'string') {
				const trimmed = v.trim();
				// 关键：循环节点或大模型输出常将子 JSON 序列化存储在字段中，深层递归解析
				if (trimmed.startsWith('{') || trimmed.startsWith('[')) {
					try {
						const sub = JSON.parse(trimmed);
						traverse(sub, fullKey);
						continue;
					} catch {
						// 降级为常规字符串处理
					}
				}
				checkAndAdd(v, k, obj);
			} else if (typeof v === 'object' && v !== null) {
				traverse(v, fullKey);
			}
		}
	}

	if (parsed) {
		traverse(parsed);
	}

	// 无论之前解析如何，若未挖出图片或文本中存在漏网的 uploads 路径，进行正则扫描兜底
	const rawStr = typeof data === 'string' ? data : JSON.stringify(data);
	if (
		rawStr &&
		(list.length === 0 || rawStr.includes('/uploads/') || rawStr.includes('uploads/'))
	) {
		const regex =
			/(?:https?:\/\/[^\s"'<>]+\.(?:png|jpe?g|webp|gif|svg|avif)(?:\?[^\s"'<>]*)?|(?:(?:\/|\b)uploads\/[^\s"'<>]+\.(?:png|jpe?g|webp|gif|svg|avif)(?:\?[^\s"'<>]*)?)|(?:(?:\/|\b)static\/[^\s"'<>]+\.(?:png|jpe?g|webp|gif|svg|avif)(?:\?[^\s"'<>]*)?))/gi;
		let m;
		while ((m = regex.exec(rawStr)) !== null) {
			const u = resolveUrl(m[0]);
			if (u && !seenUrls.has(u)) {
				seenUrls.add(u);
				list.push({ url: u, title: nodeName || 'image' });
			}
		}
	}

	return list;
}

/**
 * 每个节点自身所包含的有效图片列表（节点内部独立去重）
 * 确保循环节点、结束节点（汇总整场产物）均能完整展示属于该节点的图片产物画廊
 */
const nodeProducedImagesMap = computed<Map<any, ImageDownloadItem[]>>(() => {
	const map = new Map<any, ImageDownloadItem[]>();

	props.items.forEach((item, index) => {
		const key = item.id !== undefined && item.id !== null ? item.id : index;

		// 开始节点作为工作流纯入口参数，不作为图片产出步骤
		if (item.nodeType === 'start') {
			map.set(key, []);
			return;
		}

		// 提取该节点产物中的图片（严格优先使用本次节点执行的 outputData）
		const payload =
			item.outputData !== undefined && item.outputData !== null && item.outputData !== ''
				? item.outputData
				: item.inputData;
		const rawImages = extractRawImagesFromData(payload, item.nodeName);

		// 该节点内部根据 URL 去重
		const nodeSeen = new Set<string>();
		const uniqueImages: ImageDownloadItem[] = [];
		rawImages.forEach(img => {
			if (!nodeSeen.has(img.url)) {
				nodeSeen.add(img.url);
				uniqueImages.push(img);
			}
		});

		map.set(key, uniqueImages);
	});

	return map;
});

/**
 * 获取单个节点的图片列表
 */
function extractNodeImages(item: WorkflowLogItem): ImageDownloadItem[] {
	if (!item) return [];
	const index = props.items.indexOf(item);
	const key = item.id !== undefined && item.id !== null ? item.id : index;
	return nodeProducedImagesMap.value.get(key) || [];
}

/**
 * 收集提取整场工作流所有节点的真实图片产物（全局跨节点 URL 去重汇总）
 * 用于顶部全景指标看板显示总数以及顶部工具栏“一键全量打包下载”
 */
const allWorkflowImages = computed<ImageDownloadItem[]>(() => {
	const list: ImageDownloadItem[] = [];
	const seenUrls = new Set<string>();

	props.items.forEach(item => {
		const imgs = extractNodeImages(item);
		imgs.forEach(img => {
			if (!seenUrls.has(img.url)) {
				seenUrls.add(img.url);
				list.push(img);
			}
		});
	});

	// 兜底：若节点提取为空，从全文原始字符串扫描
	if (list.length === 0) {
		props.items.forEach(item => {
			const str = (item.outputData || '') + (item.inputData || '');
			const imgs = extractRawImagesFromData(str, item.nodeName);
			imgs.forEach(img => {
				if (!seenUrls.has(img.url)) {
					seenUrls.add(img.url);
					list.push(img);
				}
			});
		});
	}

	return list;
});

async function handleDownloadAllImages() {
	if (allWorkflowImages.value.length === 0) {
		ElMessage.warning(t('暂无生成图片产物'));
		return;
	}

	downloadingAllZip.value = true;
	downloadAllProgressText.value = `0/${allWorkflowImages.value.length}`;

	try {
		// 确保下载令牌最新有效，杜绝长时间停留导致的 401
		await ensureDownloadToken(true);

		const itemsToDownload = allWorkflowImages.value.map(img => {
			const finalUrl = assetUrl(img.url) || img.url;
			return {
				url: finalUrl,
				title: img.title,
				subtitle: img.subtitle
			};
		});

		const instId = props.items[0]?.instanceId || 'all';
		const zipName = `workflow_inst${instId}_images_${Date.now()}.zip`;
		await downloadImagesAsZip(itemsToDownload, zipName, (curr, total) => {
			downloadAllProgressText.value = `${curr}/${total}`;
		});
	} catch (e: any) {
		ElMessage.error(t('打包下载失败: ') + (e.message || e));
	} finally {
		downloadingAllZip.value = false;
		downloadAllProgressText.value = '';
	}
}

// 每个卡片当前选中的 tab 名
const activeTabs = reactive<Record<string | number, string>>({});

// 抽屉宽度
const currentDrawerSize = computed(() => {
	if (isFullscreen.value) return '100vw';
	return props.size || '820px';
});

// 统计指标
const successCount = computed(() => {
	return props.items.filter(i => i.status === 'success').length;
});

const failCount = computed(() => {
	return props.items.filter(i => i.status === 'error' || i.status === 'failed').length;
});

const totalLatencyMs = computed(() => {
	return props.items.reduce((acc, cur) => acc + (cur.latencyMs || 0), 0);
});

// AI 运行时关键观测指标：大模型调用总数与工具执行总数
const llmCount = computed(() => {
	return props.items.filter(i => i.nodeType === 'llm').length;
});

const toolCount = computed(() => {
	return props.items.filter(
		i =>
			i.nodeType === 'tool' ||
			i.nodeType === 'tool_executor' ||
			i.nodeType === 'batch_processor'
	).length;
});

function handleCopyRunSummary() {
	const total = props.items.length;
	const succ = successCount.value;
	const fail = failCount.value;
	const totalTime = formatLatency(totalLatencyMs.value);
	const llm = llmCount.value;
	const tool = toolCount.value;
	const imgs = allWorkflowImages.value.length;

	let summary = `【${props.title || t('工作流执行摘要')}】\n`;
	summary += `· ${t('步骤总数')}：${total}（${t('成功')} ${succ}，${t('失败')} ${fail}）\n`;
	summary += `· ${t('总耗时')}：${totalTime}\n`;
	summary += `· ${t('大模型调用')}：${llm} ${t('次')}\n`;
	if (tool > 0) summary += `· ${t('工具调用')}：${tool} ${t('次')}\n`;
	if (imgs > 0) summary += `· ${t('图片产物')}：${imgs} ${t('张')}\n`;
	summary += `· ${t('执行状态')}：${props.status || (fail > 0 ? t('失败') : t('成功'))}\n`;

	copyToClipboard(summary, t('执行摘要已复制'), t('复制失败'));
}

// 异常分类智能推断
function inferErrorCategory(msg: string): string {
	if (!msg) return t('执行异常');
	const lower = msg.toLowerCase();
	if (lower.includes('timeout') || lower.includes('timed out')) return 'TIMEOUT';
	if (lower.includes('connect') || lower.includes('network') || lower.includes('connection'))
		return 'NETWORK';
	if (
		lower.includes('auth') ||
		lower.includes('token') ||
		lower.includes('permission') ||
		lower.includes('401') ||
		lower.includes('403')
	)
		return 'AUTH';
	if (lower.includes('rate') || lower.includes('limit') || lower.includes('429'))
		return 'RATE_LIMIT';
	if (lower.includes('json') || lower.includes('parse') || lower.includes('syntax'))
		return 'SYNTAX';
	if (lower.includes('valid') || lower.includes('schema') || lower.includes('type'))
		return 'VALIDATION';
	return t('运行时异常');
}

const statusTagType = computed<'success' | 'danger' | 'primary' | 'warning'>(() => {
	if (props.status === 'success') return 'success';
	if (props.status === 'failed' || props.status === 'error') return 'danger';
	if (props.status === 'paused') return 'warning';
	return 'primary';
});

const statusLabel = computed(() => {
	if (!props.status) return t('准备中');
	const map: Record<string, string> = {
		pending: t('待运行'),
		running: t('运行中'),
		paused: t('已挂起'),
		success: t('成功'),
		failed: t('失败')
	};
	return map[props.status] || props.status;
});

// 节点专属元数据映射
const NODE_META_MAP: Record<
	string,
	{
		label: string;
		tagType: 'primary' | 'success' | 'warning' | 'info' | 'danger';
		icon: string;
		color: string;
		bg: string;
	}
> = {
	llm: {
		label: t('大模型'),
		tagType: 'warning',
		icon: 'llm',
		color: '#8b5cf6',
		bg: 'rgba(139, 92, 246, 0.12)'
	},
	image_generator: {
		label: t('图像生成'),
		tagType: 'success',
		icon: 'image_generator',
		color: '#10b981',
		bg: 'rgba(16, 185, 129, 0.12)'
	},
	loop_controller: {
		label: t('循环控制'),
		tagType: 'warning',
		icon: 'loop_controller',
		color: '#f59e0b',
		bg: 'rgba(245, 158, 11, 0.12)'
	},
	variable_transform: {
		label: t('变量转换'),
		tagType: 'info',
		icon: 'variable_transform',
		color: '#0ea5e9',
		bg: 'rgba(14, 165, 233, 0.12)'
	},
	variable_assignment: {
		label: t('变量赋值'),
		tagType: 'info',
		icon: 'variable_assignment',
		color: '#14b8a6',
		bg: 'rgba(20, 184, 166, 0.12)'
	},
	condition: {
		label: t('条件判断'),
		tagType: 'warning',
		icon: 'condition',
		color: '#f97316',
		bg: 'rgba(249, 115, 22, 0.12)'
	},
	switch: {
		label: t('条件分支'),
		tagType: 'warning',
		icon: 'switch',
		color: '#d946ef',
		bg: 'rgba(217, 70, 239, 0.12)'
	},
	tool_executor: {
		label: t('工具执行'),
		tagType: 'primary',
		icon: 'tool_executor',
		color: '#3b82f6',
		bg: 'rgba(59, 130, 246, 0.12)'
	},
	tool: {
		label: t('工具执行'),
		tagType: 'primary',
		icon: 'tool_executor',
		color: '#3b82f6',
		bg: 'rgba(59, 130, 246, 0.12)'
	},
	human_input: {
		label: t('人工确认'),
		tagType: 'danger',
		icon: 'human_input',
		color: '#f43f5e',
		bg: 'rgba(244, 63, 94, 0.12)'
	},
	intent_classifier: {
		label: t('意图分类'),
		tagType: 'primary',
		icon: 'intent_classifier',
		color: '#6366f1',
		bg: 'rgba(99, 102, 241, 0.12)'
	},
	start: {
		label: t('开始节点'),
		tagType: 'success',
		icon: 'start',
		color: '#22c55e',
		bg: 'rgba(34, 197, 94, 0.12)'
	},
	end: {
		label: t('结束节点'),
		tagType: 'info',
		icon: 'end',
		color: '#64748b',
		bg: 'rgba(100, 116, 139, 0.12)'
	},
	batch_processor: {
		label: t('批处理器'),
		tagType: 'primary',
		icon: 'batch_processor',
		color: '#06b6d4',
		bg: 'rgba(6, 182, 212, 0.12)'
	}
};

function getNodeMeta(type?: string) {
	if (!type || !NODE_META_MAP[type]) {
		return {
			label: type || t('步骤'),
			tagType: 'info' as const,
			icon: 'default',
			color: '#64748b',
			bg: 'rgba(100, 116, 139, 0.12)'
		};
	}
	return NODE_META_MAP[type];
}

// 筛选后的列表
const filteredItems = computed(() => {
	let list = props.items;

	// 1. 状态筛选
	if (filterStatus.value === 'success') {
		list = list.filter(i => i.status === 'success');
	} else if (filterStatus.value === 'error') {
		list = list.filter(i => i.status === 'error' || i.status === 'failed');
	} else if (filterStatus.value === 'media') {
		list = list.filter(i => hasDetectedImages(i));
	}

	// 2. 关键词模糊匹配
	const kw = searchKeyword.value.trim().toLowerCase();
	if (kw) {
		list = list.filter(item => {
			return (
				(item.nodeName && item.nodeName.toLowerCase().includes(kw)) ||
				(item.nodeId && item.nodeId.toLowerCase().includes(kw)) ||
				(item.nodeType && item.nodeType.toLowerCase().includes(kw)) ||
				(item.errorMessage && item.errorMessage.toLowerCase().includes(kw))
			);
		});
	}

	return list;
});

// 结果优先策略：智能计算节点默认展开激活的 Tab
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

// 初始化每个步骤选中的 Tab（智能结果优先）
watch(
	() => props.items,
	items => {
		items.forEach((item, index) => {
			const key = item.id || index;
			if (!activeTabs[key]) {
				activeTabs[key] = getInitialActiveTab(item);
			}
		});
	},
	{ immediate: true, deep: true }
);

function getStepIndex(item: WorkflowLogItem, fallbackIndex: number): number {
	const realIndex = props.items.indexOf(item);
	return realIndex !== -1 ? realIndex + 1 : fallbackIndex + 1;
}

function getTimelineType(status?: string): 'success' | 'danger' | 'primary' | 'info' {
	if (status === 'success') return 'success';
	if (status === 'error' || status === 'failed') return 'danger';
	if (status === 'running') return 'primary';
	return 'info';
}

function getStatusTagType(status?: string): 'success' | 'danger' | 'primary' | 'info' {
	if (status === 'success') return 'success';
	if (status === 'error' || status === 'failed') return 'danger';
	if (status === 'running') return 'primary';
	return 'info';
}

function getStatusLabel(status?: string): string {
	if (status === 'success') return t('成功');
	if (status === 'error' || status === 'failed') return t('失败');
	if (status === 'running') return t('运行中');
	return status || '-';
}

function getLatencyTagType(ms?: number): 'success' | 'warning' | 'danger' | 'info' {
	if (!ms) return 'info';
	if (ms > 30000) return 'danger';
	if (ms > 5000) return 'warning';
	return 'info';
}

function formatLatency(ms?: number): string {
	if (ms === undefined || ms === null || isNaN(ms)) return '-';
	if (ms < 1000) return `${ms}ms`;
	if (ms < 60000) return `${(ms / 1000).toFixed(1)}s`;
	const min = Math.floor(ms / 60000);
	const sec = ((ms % 60000) / 1000).toFixed(1);
	return `${min}m ${sec}s`;
}

function formatTime(value?: string): string {
	return value ? dayjs(value).format(props.timeFormat) : '-';
}

function formatShortTime(value?: string): string {
	return value ? dayjs(value).format('HH:mm:ss') : '-';
}

function formatFullTime(value?: string): string {
	return value ? dayjs(value).format('YYYY-MM-DD HH:mm:ss') : '-';
}

function toggleExpand(item: WorkflowLogItem) {
	item.isExpanded = !item.isExpanded;
}

function handleExpandAll() {
	props.items.forEach(i => (i.isExpanded = true));
	emit('expand-all');
}

function handleCollapseAll() {
	props.items.forEach(i => (i.isExpanded = false));
	emit('collapse-all');
}

function handleExpandErrorsOnly() {
	props.items.forEach(i => {
		i.isExpanded = i.status === 'error' || i.status === 'failed';
	});
}

function copyNodeId(nodeId: string) {
	copyToClipboard(nodeId, t('节点ID已复制'), t('复制失败'));
}

function copyErrorMessage(msg: string) {
	copyToClipboard(msg, t('复制成功'), t('复制失败'));
}

// 辅助检测：是否含有图片产物（基于精确提取与节点类型过滤）
function hasDetectedImages(item: WorkflowLogItem): boolean {
	return extractNodeImages(item).length > 0;
}

function getImageCount(item: WorkflowLogItem): number {
	return extractNodeImages(item).length;
}

// 辅助检测：是否含有故事或长文案业务结构
function hasStoryOrCopyContent(item: WorkflowLogItem): boolean {
	const str = item.outputData || '';
	return (
		str.includes('copy_text') ||
		str.includes('story_text') ||
		str.includes('paragraphs') ||
		str.includes('paragraphs_array') ||
		str.includes('plan_output')
	);
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
