<template>
	<div class="ai-image-workbench">
		<!-- 左侧：参数与提示词配置面板 -->
		<section class="generator">
			<!-- 面板顶部标题 -->
			<header class="generator__head">
				<div class="head-info">
					<div class="head-title">
						<el-icon class="title-icon"><magic-stick /></el-icon>
						<h2>{{ $t('AI 生图工作台') }}</h2>
					</div>
					<span class="head-summary">{{ selectedProfileSummary }}</span>
				</div>
				<el-tag :type="providerKindTag.type" effect="plain" round class="provider-tag">
					{{ providerKindTag.label }}
				</el-tag>
			</header>

			<!-- 可滚动的内容区 -->
			<div class="generator__body">
				<!-- 顶部温馨提示条 -->
				<div v-if="showTopNotice" class="top-notice">
					<div class="top-notice__body">
						<el-icon class="notice-icon"><bell /></el-icon>
						<span class="notice-text">
							{{ $t('不同模型支持的图生图、尺寸规格和专属参数存在差异，可悬停各标题旁的小图标查看说明。') }}
						</span>
					</div>
					<el-icon class="close-icon" @click="closeTopNotice"><close /></el-icon>
				</div>

				<!-- 1. 调用配置 -->
				<div class="config-card">
					<div class="card-header">
						<span class="card-title">{{ $t('调用配置') }}</span>
					</div>
					<div class="field-grid">
						<cl-select
							v-model="form.profileCode"
							:options="profileOptions"
							:placeholder="$t('默认图片配置')"
							clearable
						/>
						<el-input v-model="form.scenario" :placeholder="$t('场景编码 (如 default)')" clearable />
					</div>

					<div v-if="selectedProfile" class="profile-meta">
						<el-tag size="small" effect="light">{{ selectedProfile.providerName || '-' }}</el-tag>
						<el-tag size="small" type="success" effect="light">
							{{ selectedProfile.modelName || selectedProfile.modelId }}
						</el-tag>
						<el-tag size="small" type="info" effect="plain">
							{{ selectedProfile.modelType || 'image' }}
						</el-tag>
						<el-tag
							v-for="item in capabilityTags"
							:key="item"
							size="small"
							type="warning"
							effect="plain"
						>
							{{ item }}
						</el-tag>
					</div>
				</div>

				<!-- 2. 正向提示词 -->
				<div class="config-card">
					<div class="card-header space-between">
						<div class="title-with-tip">
							<span class="card-title">{{ $t('提示词 (Prompt)') }}</span>
						</div>
						<div class="header-tools">
							<el-button link type="primary" size="small" @click="fillSamplePrompt">
								<el-icon class="mr-2"><magic-stick /></el-icon>
								{{ $t('示例灵感') }}
							</el-button>
							<el-button link size="small" @click="form.prompt = ''">
								<el-icon class="mr-2"><delete /></el-icon>
								{{ $t('清空') }}
							</el-button>
						</div>
					</div>

					<div class="prompt-box">
						<el-input
							v-model="form.prompt"
							type="textarea"
							:rows="5"
							resize="none"
							class="prompt-textarea"
							:placeholder="$t('描述想要生成的画面内容、艺术风格、光影构图、色彩与细节... 支持按 Ctrl + Enter 快速生成')"
							@keydown="handlePromptKeydown"
						/>
						<div class="prompt-footer">
							<span class="shortcut-tip">{{ $t('按 Ctrl + Enter 快捷生成') }}</span>
							<span
								class="counter-tip"
								:class="{
									'is-limit':
										(isErnieIrag && form.prompt.length > 220) ||
										(activeLimits.max_prompt_length &&
											form.prompt.length > activeLimits.max_prompt_length)
								}"
							>
								{{ form.prompt.length }}
								<template v-if="isErnieIrag">/ 220</template>
								<template v-else-if="activeLimits.max_prompt_length">
									/ {{ activeLimits.max_prompt_length }}
								</template>
							</span>
						</div>
					</div>

					<!-- 超长告警 -->
					<div v-if="isErnieIrag && form.prompt.length > 220" class="field-tip warning">
						<el-icon><info-filled /></el-icon>
						<span>{{ $t('提示：当前为 ERNIE iRAG 检索增强生图，Prompt 长度超过 220 字符限额，后端将自动截断。') }}</span>
					</div>
					<div
						v-if="
							!isErnieIrag &&
							activeLimits.max_prompt_length &&
							form.prompt.length > activeLimits.max_prompt_length
						"
						class="field-tip warning"
					>
						<el-icon><info-filled /></el-icon>
						<span>
							{{ $t('提示：当前 Prompt 长度已超过模型推荐限制（最大') }}
							{{ activeLimits.max_prompt_length }} {{ $t('字符）。') }}
						</span>
					</div>

					<!-- 负向提示词 (阿里百炼等模型支持) -->
					<div v-if="showBailianNegativePrompt" class="negative-prompt-box">
						<div class="sub-title">
							<span>{{ $t('负向提示词 (Negative Prompt)') }}</span>
							<el-button link size="small" type="primary" @click="fillDefaultNegativePrompt">
								{{ $t('常用滤镜') }}
							</el-button>
						</div>
						<el-input
							v-model="form.negativePrompt"
							type="textarea"
							:rows="2"
							resize="none"
							:placeholder="$t('不想在画面中出现的元素，如：低清晰度、畸形手足、色偏、文字水印、粗糙质感')"
						/>
					</div>
				</div>

				<!-- 3. 参考图片 (图生图) -->
				<div class="config-card">
					<div class="card-header space-between">
						<div class="title-with-tip">
							<span class="card-title">{{ $t('参考图片 (图生图)') }}</span>
							<el-tooltip
								:content="$t('仅在火山方舟、阿里百炼、谷歌 Gemini 和 OpenAI 兼容等支持图生图的模型下生效。')"
								placement="top"
							>
								<el-icon class="title-tip-icon"><info-filled /></el-icon>
							</el-tooltip>
						</div>
						<el-radio-group v-model="imageInputMode" size="small">
							<el-radio-button value="upload">{{ $t('本地上传') }}</el-radio-button>
							<el-radio-button value="url">{{ $t('图片地址') }}</el-radio-button>
						</el-radio-group>
					</div>

					<div class="reference-input-area">
						<div v-if="imageInputMode === 'upload'" class="upload-wrapper">
							<cl-upload v-model="form.image" :limit="1" />
							<span v-if="!form.image" class="upload-hint">{{ $t('支持拖拽或点击上传单张参考底图') }}</span>
						</div>
						<div v-else class="url-input-wrapper">
							<el-input
								v-model="form.image"
								:placeholder="$t('请输入参考图片的公开 HTTP/HTTPS 地址')"
								clearable
							>
								<template #prefix>
									<el-icon><picture /></el-icon>
								</template>
							</el-input>
							<div v-if="form.image" class="url-image-preview">
								<el-image :src="form.image" fit="cover" class="preview-thumb" />
								<el-button link type="danger" size="small" @click="form.image = ''">
									{{ $t('移除') }}
								</el-button>
							</div>
						</div>
					</div>
				</div>

				<!-- 4. 生图参数配置 -->
				<div class="config-card">
					<div class="card-header">
						<div class="title-with-tip">
							<span class="card-title">{{ $t('生图参数') }}</span>
							<el-tooltip v-if="sizeHint" :content="sizeHint" placement="top">
								<el-icon class="title-tip-icon"><info-filled /></el-icon>
							</el-tooltip>
						</div>
					</div>

					<!-- 快速比例快捷切换胶囊 -->
					<div class="aspect-ratio-selector">
						<span class="ratio-label">{{ $t('常用比例:') }}</span>
						<div class="ratio-chips">
							<button
								v-for="ratio in COMMON_RATIOS"
								:key="ratio.key"
								type="button"
								class="ratio-chip"
								:class="{ 'is-active': isRatioActive(ratio.key) }"
								@click="selectRatio(ratio.key)"
							>
								<span class="ratio-icon" :class="ratio.iconClass"></span>
								<span class="ratio-name">{{ ratio.label }}</span>
							</button>
						</div>
					</div>

					<!-- 规整双列参数 -->
					<div class="field-grid field-grid--compact mt-10">
						<el-form-item :label="$t('尺寸规格')">
							<el-select
								v-model="form.size"
								filterable
								:allow-create="allowCustomSize"
								default-first-option
								clearable
								style="width: 100%"
							>
								<el-option
									v-for="item in availableSizeOptions"
									:key="item.value"
									:label="item.label"
									:value="item.value"
								/>
							</el-select>
						</el-form-item>

						<el-form-item :label="$t('生成张数')">
							<el-input-number
								v-model="form.n"
								:min="1"
								:max="activeLimits.max_n || 8"
								controls-position="right"
								style="width: 100%"
							/>
						</el-form-item>

						<el-form-item :label="$t('返回格式')">
							<cl-select
								v-model="form.responseFormat"
								:options="RESPONSE_FORMAT_OPTIONS"
								style="width: 100%"
							/>
						</el-form-item>

						<el-form-item v-if="showWatermarkOption" :label="$t('平台水印')">
							<el-switch v-model="form.watermark" active-text="开启" inactive-text="关闭" inline-prompt />
						</el-form-item>
					</div>
				</div>

				<!-- 5. 厂商专属参数 -->
				<image-provider-params
					:form="form"
					:provider-kind="providerKind"
					:provider-hint="providerHint"
					:is-ernie-irag="isErnieIrag"
				/>

				<!-- 6. 高级参数 JSON (默认收起) -->
				<div class="config-card config-card--collapse">
					<el-collapse>
						<el-collapse-item name="advanced">
							<template #title>
								<div class="collapse-title">
									<el-icon><setting /></el-icon>
									<span>{{ $t('高级参数 JSON') }}</span>
									<span class="collapse-sub">{{ $t('(请求前自动深合并)') }}</span>
								</div>
							</template>
							<div class="advanced-editor">
								<div class="advanced-tools">
									<span class="tool-note">{{ $t('可覆盖或透传专属参数（如 quality, seed, lora 等）') }}</span>
									<div class="tool-buttons">
										<el-button link size="small" type="primary" @click="formatOptionsJson">
											{{ $t('格式化') }}
										</el-button>
										<el-button link size="small" @click="resetOptions">
											{{ $t('重置') }}
										</el-button>
									</div>
								</div>
								<el-input
									v-model="form.optionsText"
									type="textarea"
									:rows="5"
									font-family="monospace"
									class="code-textarea"
								/>
							</div>
						</el-collapse-item>
					</el-collapse>
				</div>
			</div>

			<!-- 底部固定常驻操作栏 (无论左侧怎么滚动永远可见！) -->
			<footer class="generator__footer">
				<div class="footer-left">
					<el-button plain size="default" @click="clearResult">
						<el-icon class="mr-2"><refresh /></el-icon>
						{{ $t('清空') }}
					</el-button>
				</div>
				<div class="footer-right">
					<el-button
						:loading="loading.submit"
						type="warning"
						plain
						size="default"
						@click="submitTask"
					>
						{{ $t('异步提交任务') }}
					</el-button>
					<el-button
						:loading="loading.generate"
						type="primary"
						size="default"
						class="generate-main-btn"
						@click="generate"
					>
						<el-icon v-if="!loading.generate" class="mr-2"><magic-stick /></el-icon>
						<span>{{ loading.generate ? $t('正在生成...') : $t('立即生成') }}</span>
					</el-button>
				</div>
			</footer>
		</section>

		<!-- 右侧：生成结果画廊与调试区 -->
		<aside class="result">
			<!-- 顶部状态与统计条 -->
			<header class="result__head">
				<div class="result-title-group">
					<div class="title-row">
						<el-icon class="gallery-icon"><picture /></el-icon>
						<span class="title-text">{{ $t('生成画廊') }}</span>
					</div>
					<div v-if="resultMeta.length" class="meta-row">
						<el-tag
							v-for="(meta, idx) in resultMeta"
							:key="idx"
							size="small"
							effect="plain"
							class="meta-badge"
						>
							{{ meta }}
						</el-tag>
					</div>
				</div>

				<div class="result-head-actions">
					<el-tag v-if="imageItems.length" type="success" effect="dark" round>
						{{ $t('已生成') }} {{ imageItems.length }} {{ $t('张') }}
					</el-tag>
					<el-button
						v-if="imageItems.length"
						link
						size="small"
						type="primary"
						@click="copyAllImageUrls"
					>
						<el-icon class="mr-2"><document-copy /></el-icon>
						{{ $t('复制全部链接') }}
					</el-button>
				</div>
			</header>

			<!-- 核心展示区 -->
			<div class="result__body">
				<!-- 1. 异步任务提交成功状态 -->
				<div v-if="taskSubmitted" class="task-result">
					<el-result
						icon="success"
						:title="$t('异步生图任务已提交')"
						:sub-title="`Task ID: ${taskSubmitted.taskId}`"
					>
						<template #extra>
							<div class="task-buttons">
								<el-button type="primary" @click="copyText(String(taskSubmitted.taskId))">
									<el-icon class="mr-2"><copy-document /></el-icon>
									{{ $t('复制任务 ID') }}
								</el-button>
								<el-button @click="navigateToTasks">
									{{ $t('前往任务列表') }}
								</el-button>
							</div>
						</template>
					</el-result>
				</div>

				<!-- 2. 生成中高亮加载态骨架屏 -->
				<div v-else-if="loading.generate" class="generating-state">
					<div class="pulse-loader">
						<div class="spinner-ring"></div>
						<el-icon class="pulse-icon"><magic-stick /></el-icon>
					</div>
					<h3 class="generating-title">{{ $t('AI 正在绘制画面中...') }}</h3>
					<p class="generating-desc">{{ $t('正在调度算力与模型推理渲染，通常需要 3 ~ 15 秒，请稍候') }}</p>
					<div class="generating-skeleton-cards">
						<div v-for="n in form.n || 1" :key="n" class="skeleton-card">
							<div class="shimmer-block"></div>
						</div>
					</div>
				</div>

				<!-- 3. 图片画廊网格 -->
				<div v-else-if="imageItems.length" class="gallery-grid">
					<div
						v-for="(item, index) in imageItems"
						:key="index"
						class="gallery-card"
					>
						<div class="image-wrapper">
							<el-image
								class="gallery-image"
								:src="item.src"
								fit="contain"
								:preview-src-list="previewUrls"
								:initial-index="index"
								preview-teleported
								loading="lazy"
							>
								<template #placeholder>
									<div class="image-loading-placeholder">
										<el-icon class="is-loading"><refresh /></el-icon>
										<span>{{ $t('加载图像中...') }}</span>
									</div>
								</template>
								<template #error>
									<div class="image-error-placeholder">
										<el-icon><picture /></el-icon>
										<span>{{ $t('图片加载失败') }}</span>
									</div>
								</template>
							</el-image>

							<!-- 悬浮操作栏 (底部半透明磨砂) -->
							<div class="image-hover-overlay">
								<el-tooltip :content="$t('大图全屏预览')" placement="top">
									<button
										type="button"
										class="action-icon-btn"
										@click.stop="triggerPreview(index)"
									>
										<el-icon><zoom-in /></el-icon>
									</button>
								</el-tooltip>

								<el-tooltip :content="$t('下载原图到本地')" placement="top">
									<button
										type="button"
										class="action-icon-btn"
										@click.stop="downloadImage(item.src, index)"
									>
										<el-icon><download /></el-icon>
									</button>
								</el-tooltip>

								<el-tooltip :content="$t('复制图片地址')" placement="top">
									<button
										type="button"
										class="action-icon-btn"
										@click.stop="copyText(item.value)"
									>
										<el-icon><copy-document /></el-icon>
									</button>
								</el-tooltip>

								<el-tooltip :content="$t('设为参考图 (图生图)')" placement="top">
									<button
										type="button"
										class="action-icon-btn"
										@click.stop="useAsReference(item.src)"
									>
										<el-icon><connection /></el-icon>
									</button>
								</el-tooltip>

								<el-tooltip v-if="item.url" :content="$t('新标签页打开')" placement="top">
									<button
										type="button"
										class="action-icon-btn"
										@click.stop="openUrl(item.url)"
									>
										<el-icon><top-right /></el-icon>
									</button>
								</el-tooltip>
							</div>
						</div>

						<div class="card-caption">
							<span class="index-num">#{{ index + 1 }}</span>
							<span class="format-tag">{{ form.size || 'Auto' }}</span>
						</div>
					</div>
				</div>

				<!-- 4. 空状态提示 -->
				<div v-else class="empty-gallery">
					<div class="empty-graphic">
						<el-icon class="empty-icon"><picture /></el-icon>
					</div>
					<h3 class="empty-title">{{ $t('等待生图指令') }}</h3>
					<p class="empty-desc">
						{{ $t('在左侧配置模型、输入提示词并调整尺寸后，点击「立即生成」即可在此处查看渲染成果。') }}
					</p>
					<el-button type="primary" plain @click="fillSamplePrompt">
						<el-icon class="mr-2"><magic-stick /></el-icon>
						{{ $t('填入示例灵感试一试') }}
					</el-button>
				</div>
			</div>

			<!-- 底部折叠信息与报文审计 -->
			<footer class="result__inspector">
				<el-collapse>
					<el-collapse-item name="debug">
						<template #title>
							<div class="inspector-title">
								<el-icon><info-filled /></el-icon>
								<span>{{ $t('请求与响应数据报文') }}</span>
								<el-tag v-if="result?.requestId" size="small" type="info" class="ml-2">
									ID: {{ result.requestId }}
								</el-tag>
							</div>
						</template>

						<!-- 元数据属性列表 -->
						<div v-if="result" class="inspector-meta-grid">
							<div class="meta-item">
								<span class="meta-k">Provider</span>
								<span class="meta-v">{{ result.provider || '-' }}</span>
							</div>
							<div class="meta-item">
								<span class="meta-k">Model</span>
								<span class="meta-v">{{ result.model || '-' }}</span>
							</div>
							<div class="meta-item">
								<span class="meta-k">Profile</span>
								<span class="meta-v">{{ result.profile || '-' }}</span>
							</div>
							<div class="meta-item">
								<span class="meta-k">Request / Task ID</span>
								<span class="meta-v">{{ result.requestId || result.taskId || '-' }}</span>
							</div>
						</div>

						<!-- 报文原始 JSON Tabs -->
						<el-tabs class="raw-tabs">
							<el-tab-pane :label="$t('请求报文')">
								<div class="json-box">
									<el-button
										v-if="lastPayload"
										size="small"
										class="json-copy-btn"
										@click="copyJson(lastPayload)"
									>
										{{ $t('复制 JSON') }}
									</el-button>
									<pre>{{ formatJson(lastPayload) }}</pre>
								</div>
							</el-tab-pane>
							<el-tab-pane :label="$t('响应数据')">
								<div class="json-box">
									<el-button
										v-if="result"
										size="small"
										class="json-copy-btn"
										@click="copyJson(result)"
									>
										{{ $t('复制 JSON') }}
									</el-button>
									<pre>{{ formatJson(result) }}</pre>
								</div>
							</el-tab-pane>
						</el-tabs>
					</el-collapse-item>
				</el-collapse>
			</footer>
		</aside>
	</div>
</template>

<script lang="ts" setup>
defineOptions({
	name: 'ai-image'
});

import { ref, watch } from 'vue';
import { useRouter } from 'vue-router';
import { ElMessage } from 'element-plus';
import { useI18n } from 'vue-i18n';
import {
	Bell,
	Close,
	InfoFilled,
	MagicStick,
	Picture,
	Download,
	CopyDocument,
	Delete,
	Refresh,
	Connection,
	ZoomIn,
	DocumentCopy,
	TopRight,
	Setting
} from '@element-plus/icons-vue';
import { RESPONSE_FORMAT_OPTIONS } from '../utils/image-providers';
import { useImageWorkbench } from '../composables/use-image-workbench';
import ImageProviderParams from '../components/image-provider-params.vue';

const { t } = useI18n();
const router = useRouter();

const {
	form,
	result,
	lastPayload,
	loading,
	selectedProfile,
	selectedProfileSummary,
	profileOptions,
	providerKind,
	showBailianNegativePrompt,
	showWatermarkOption,
	availableSizeOptions,
	allowCustomSize,
	activeLimits,
	sizeHint,
	providerKindTag,
	providerHint,
	capabilityTags,
	imageItems,
	previewUrls,
	taskSubmitted,
	resultMeta,
	isErnieIrag,
	generate,
	submitTask,
	resetOptions,
	clearResult
} = useImageWorkbench();

// 顶部提示条持久化收起
const showTopNotice = ref(localStorage.getItem('loom_ai_image_notice_closed') !== 'true');

function closeTopNotice() {
	showTopNotice.value = false;
	localStorage.setItem('loom_ai_image_notice_closed', 'true');
}

// 参考图模式
const imageInputMode = ref('upload');

watch(imageInputMode, () => {
	if (typeof form.image !== 'string') {
		form.image = '';
	}
});

// 常用生图比例定义
interface AspectRatioItem {
	key: string;
	label: string;
	iconClass: string;
}

const COMMON_RATIOS: AspectRatioItem[] = [
	{ key: '1:1', label: '1:1 方形', iconClass: 'icon-square' },
	{ key: '16:9', label: '16:9 电脑横屏', iconClass: 'icon-landscape' },
	{ key: '9:16', label: '9:16 手机竖屏', iconClass: 'icon-portrait' },
	{ key: '4:3', label: '4:3 标准横向', iconClass: 'icon-standard-h' },
	{ key: '3:4', label: '3:4 经典竖向', iconClass: 'icon-standard-v' }
];

// 判断比例是否激活
function isRatioActive(ratioKey: string): boolean {
	const curSize = String(form.size || '').toLowerCase();
	if (curSize === ratioKey) {
		return true;
	}
	// 百炼/火山等显式尺寸：包含比例说明
	if (curSize.includes(ratioKey)) {
		return true;
	}
	// 尺寸解析匹配
	const [w, h] = curSize.split('x').map(Number);
	if (w && h) {
		const ratio = (w / h).toFixed(2);
		if (ratioKey === '1:1' && ratio === '1.00') return true;
		if (ratioKey === '16:9' && (ratio === '1.78' || ratio === '1.75')) return true;
		if (ratioKey === '9:16' && (ratio === '0.56' || ratio === '0.57')) return true;
		if (ratioKey === '4:3' && ratio === '1.33') return true;
		if (ratioKey === '3:4' && ratio === '0.75') return true;
	}
	return false;
}

// 选中比例，自动从当前模型支持的可用尺寸列表中匹配最相符的尺寸
function selectRatio(ratioKey: string) {
	const options = availableSizeOptions.value;
	// 1. 优先直接匹配完全相等的 value（如 ToAPIs 的 "1:1", "16:9"）
	const exact = options.find(opt => opt.value === ratioKey);
	if (exact) {
		form.size = exact.value;
		return;
	}
	// 2. 查找 label 或 value 包含该比例字符串的选项（如 "1280x720（16:9）"）
	const foundByLabel = options.find(
		opt => opt.label.includes(ratioKey) || opt.value.includes(ratioKey)
	);
	if (foundByLabel) {
		form.size = foundByLabel.value;
		return;
	}
	// 3. 计算宽高比例寻找数值最相近的选项
	const targetRatios: Record<string, number> = {
		'1:1': 1.0,
		'16:9': 16 / 9,
		'9:16': 9 / 16,
		'4:3': 4 / 3,
		'3:4': 3 / 4
	};
	const target = targetRatios[ratioKey];
	if (target) {
		let bestOption = options[0];
		let minDiff = Infinity;
		for (const opt of options) {
			const [w, h] = opt.value.split('x').map(Number);
			if (w && h) {
				const diff = Math.abs(w / h - target);
				if (diff < minDiff) {
					minDiff = diff;
					bestOption = opt;
				}
			}
		}
		if (bestOption && minDiff < 0.1) {
			form.size = bestOption.value;
			return;
		}
	}
	// 4. 若允许自定义则直接赋比例值
	if (allowCustomSize.value) {
		form.size = ratioKey;
	}
}

// 灵感示例库
const SAMPLE_PROMPTS = [
	'赛博朋克未来都市，雨夜霓虹灯倒影，飞行汽车穿梭，高质量细节，8k 分辨率，虚幻引擎5渲染风格',
	'水墨画风格的江南水乡，小桥流水人家，细雨蒙蒙，远山如黛，留白意境，大师级笔触',
	'一只毛茸茸的宇航员猫咪在火星表面漫步，身穿细致的太空宇航服，头盔反射星空，3D 皮克斯动画风格',
	'极简主义现代科技产品海报，漂浮的发光晶体，磨砂玻璃质感，柔和工作室灯光，纯净构图'
];

function fillSamplePrompt() {
	const randomIndex = Math.floor(Math.random() * SAMPLE_PROMPTS.length);
	form.prompt = SAMPLE_PROMPTS[randomIndex];
	ElMessage.success(t('已填入灵感提示词'));
}

// 常用负向词一键填充
function fillDefaultNegativePrompt() {
	form.negativePrompt = '低清晰度, 模糊, 畸形肢体, 多余手指, 色偏, 噪点, 粗糙质感, 水印, 签名, 裁剪不全';
	ElMessage.success(t('已填入常用负向提示词'));
}

// 监听键盘 Ctrl+Enter / Cmd+Enter 快速生成
function handlePromptKeydown(e: KeyboardEvent | Event) {
	if ('key' in e && (e.ctrlKey || e.metaKey) && e.key === 'Enter') {
		e.preventDefault();
		if (!loading.generate) {
			generate();
		}
	}
}

// 格式化高级选项 JSON
function formatOptionsJson() {
	try {
		const parsed = JSON.parse(form.optionsText || '{}');
		form.optionsText = JSON.stringify(parsed, null, 2);
		ElMessage.success(t('JSON 格式化成功'));
	} catch (e: any) {
		ElMessage.error(t('JSON 语法错误，请检查'));
	}
}

// 设为参考图
function useAsReference(src: string) {
	imageInputMode.value = 'url';
	form.image = src;
	ElMessage.success(t('已将所选图片设为参考图'));
}

// 触发大图预览（Element Plus）
function triggerPreview(index: number) {
	const images = document.querySelectorAll('.gallery-image img');
	if (images && images[index]) {
		(images[index] as HTMLElement).click();
	}
}

// 原图下载
function downloadImage(url: string, index: number) {
	try {
		if (url.startsWith('data:')) {
			const link = document.createElement('a');
			link.href = url;
			link.download = `ai-image-${Date.now()}-${index + 1}.png`;
			document.body.appendChild(link);
			link.click();
			document.body.removeChild(link);
			ElMessage.success(t('已开始下载'));
			return;
		}
		// 网络图片通过新窗口/Fetch 下载
		fetch(url)
			.then(res => res.blob())
			.then(blob => {
				const blobUrl = window.URL.createObjectURL(blob);
				const link = document.createElement('a');
				link.href = blobUrl;
				link.download = `ai-image-${Date.now()}-${index + 1}.png`;
				document.body.appendChild(link);
				link.click();
				document.body.removeChild(link);
				window.URL.revokeObjectURL(blobUrl);
				ElMessage.success(t('已开始下载'));
			})
			.catch(() => {
				// 若存在跨域直接新标签页打开
				window.open(url, '_blank');
			});
	} catch (err) {
		window.open(url, '_blank');
	}
}

// 复制文本辅助
async function copyText(value: string) {
	if (!value) return;
	await navigator.clipboard.writeText(value);
	ElMessage.success(t('已复制到剪贴板'));
}

// 复制全部图片 URL
async function copyAllImageUrls() {
	const urls = imageItems.value.map(item => item.value).join('\n');
	if (!urls) return;
	await navigator.clipboard.writeText(urls);
	ElMessage.success(t('已复制所有图片地址'));
}

// 复制 JSON
async function copyJson(data: any) {
	if (!data) return;
	await navigator.clipboard.writeText(JSON.stringify(data, null, 2));
	ElMessage.success(t('已复制 JSON 报文'));
}

// 新标签页打开链接
function openUrl(url: string) {
	window.open(url, '_blank');
}

// 跳转到任务列表
function navigateToTasks() {
	router.push('/ai/task');
}

// 格式化展示 JSON
function formatJson(value: any) {
	if (!value) {
		return '-';
	}
	return JSON.stringify(value, null, 2);
}
</script>

<style lang="scss" scoped>
.ai-image-workbench {
	display: grid;
	grid-template-columns: minmax(420px, 460px) minmax(0, 1fr);
	gap: 14px;
	height: calc(100vh - 110px);
	min-height: 680px;
	box-sizing: border-box;
}

/* ================== 左侧配置生成面板 ================== */
.generator {
	display: flex;
	flex-direction: column;
	min-height: 0;
	height: 100%;
	background: var(--el-bg-color);
	border: 1px solid var(--el-border-color-light);
	border-radius: 8px;
	box-shadow: 0 1px 4px rgba(0, 0, 0, 0.03);
	overflow: hidden;

	&__head {
		display: flex;
		align-items: center;
		justify-content: space-between;
		padding: 12px 16px;
		background: var(--el-fill-color-blank);
		border-bottom: 1px solid var(--el-border-color-lighter);
		flex-shrink: 0;

		.head-info {
			display: flex;
			flex-direction: column;
			gap: 2px;
		}

		.head-title {
			display: flex;
			align-items: center;
			gap: 6px;

			.title-icon {
				font-size: 18px;
				color: var(--el-color-primary);
			}

			h2 {
				margin: 0;
				font-size: 16px;
				font-weight: 650;
				color: var(--el-text-color-primary);
			}
		}

		.head-summary {
			font-size: 12px;
			color: var(--el-text-color-secondary);
			max-width: 280px;
			overflow: hidden;
			text-overflow: ellipsis;
			white-space: nowrap;
		}
	}

	&__body {
		flex: 1;
		min-height: 0;
		overflow-y: auto;
		padding: 12px 14px;
		display: flex;
		flex-direction: column;
		gap: 12px;

		&::-webkit-scrollbar {
			width: 6px;
		}
		&::-webkit-scrollbar-thumb {
			background: var(--el-border-color-light);
			border-radius: 3px;
		}
	}

	/* 底部常驻固钉栏 */
	&__footer {
		position: sticky;
		bottom: 0;
		z-index: 10;
		display: flex;
		align-items: center;
		justify-content: space-between;
		padding: 10px 16px;
		background: var(--el-bg-color);
		border-top: 1px solid var(--el-border-color-light);
		box-shadow: 0 -4px 12px rgba(0, 0, 0, 0.04);
		flex-shrink: 0;

		.footer-right {
			display: flex;
			align-items: center;
			gap: 8px;
		}

		.generate-main-btn {
			font-weight: 600;
			padding-left: 20px;
			padding-right: 20px;
			background: linear-gradient(135deg, var(--el-color-primary) 0%, #409eff 100%);
			box-shadow: 0 2px 8px rgba(64, 158, 255, 0.35);
			transition: all 0.2s ease;

			&:hover {
				transform: translateY(-1px);
				box-shadow: 0 4px 12px rgba(64, 158, 255, 0.45);
			}
		}
	}
}

/* 顶部提示条 */
.top-notice {
	display: flex;
	align-items: flex-start;
	justify-content: space-between;
	gap: 10px;
	padding: 8px 12px;
	background: var(--el-color-primary-light-9);
	border: 1px solid var(--el-color-primary-light-8);
	border-radius: 6px;

	&__body {
		display: flex;
		align-items: flex-start;
		gap: 8px;
		font-size: 12px;
		line-height: 1.5;
		color: var(--el-color-primary);

		.notice-icon {
			font-size: 15px;
			margin-top: 2px;
			flex-shrink: 0;
		}
	}

	.close-icon {
		font-size: 14px;
		color: var(--el-color-primary-light-3);
		cursor: pointer;
		margin-top: 2px;
		transition: color 0.2s;

		&:hover {
			color: var(--el-color-primary);
		}
	}
}

/* 配置卡片 */
.config-card {
	background: var(--el-fill-color-blank);
	border: 1px solid var(--el-border-color-lighter);
	border-radius: 6px;
	padding: 12px;
	transition: border-color 0.2s;

	&:hover {
		border-color: var(--el-border-color);
	}

	.card-header {
		display: flex;
		align-items: center;
		margin-bottom: 8px;

		&.space-between {
			justify-content: space-between;
		}

		.card-title {
			font-size: 13px;
			font-weight: 650;
			color: var(--el-text-color-primary);
		}

		.title-with-tip {
			display: flex;
			align-items: center;
			gap: 6px;
		}

		.title-tip-icon {
			font-size: 14px;
			color: var(--el-text-color-placeholder);
			cursor: pointer;
			&:hover {
				color: var(--el-color-primary);
			}
		}

		.header-tools {
			display: flex;
			align-items: center;
			gap: 8px;
		}
	}

	&--collapse {
		padding: 0 12px;
		:deep(.el-collapse) {
			border: none;
		}
		:deep(.el-collapse-item__header) {
			border: none;
			height: 40px;
			font-size: 13px;
		}
		:deep(.el-collapse-item__wrap) {
			border: none;
		}
	}
}

.field-grid {
	display: grid;
	grid-template-columns: 1fr 1fr;
	gap: 10px;

	:deep(.el-form-item) {
		margin-bottom: 0;
	}

	&--compact {
		grid-template-columns: 1fr 1fr;
	}
}

.profile-meta {
	display: flex;
	flex-wrap: wrap;
	gap: 6px;
	margin-top: 8px;
	padding-top: 8px;
	border-top: 1px dashed var(--el-border-color-lighter);
}

/* 提示词输入专区 */
.prompt-box {
	position: relative;
	border: 1px solid var(--el-border-color-light);
	border-radius: 6px;
	overflow: hidden;
	transition: all 0.2s ease;

	&:focus-within {
		border-color: var(--el-color-primary);
		box-shadow: 0 0 0 2px var(--el-color-primary-light-8);
	}

	:deep(.el-textarea__inner) {
		box-shadow: none !important;
		border: none !important;
		padding: 10px 12px;
		font-size: 13px;
		line-height: 1.6;
		background: transparent;
	}

	.prompt-footer {
		display: flex;
		align-items: center;
		justify-content: space-between;
		padding: 6px 10px;
		background: var(--el-fill-color-light);
		border-top: 1px solid var(--el-border-color-lighter);
		font-size: 11px;
		color: var(--el-text-color-secondary);

		.counter-tip.is-limit {
			color: var(--el-color-danger);
			font-weight: bold;
		}
	}
}

.negative-prompt-box {
	margin-top: 10px;
	padding-top: 10px;
	border-top: 1px dashed var(--el-border-color-lighter);

	.sub-title {
		display: flex;
		align-items: center;
		justify-content: space-between;
		margin-bottom: 6px;
		font-size: 12px;
		font-weight: 600;
		color: var(--el-text-color-regular);
	}
}

/* 比例快捷切换栏 */
.aspect-ratio-selector {
	display: flex;
	align-items: center;
	gap: 8px;
	margin-top: 4px;
	margin-bottom: 8px;
	padding: 6px 8px;
	background: var(--el-fill-color-light);
	border-radius: 6px;

	.ratio-label {
		font-size: 12px;
		color: var(--el-text-color-secondary);
		white-space: nowrap;
	}

	.ratio-chips {
		display: flex;
		flex-wrap: wrap;
		gap: 6px;
	}

	.ratio-chip {
		display: inline-flex;
		align-items: center;
		gap: 4px;
		padding: 3px 8px;
		font-size: 11px;
		background: var(--el-bg-color);
		border: 1px solid var(--el-border-color-light);
		border-radius: 4px;
		cursor: pointer;
		color: var(--el-text-color-regular);
		transition: all 0.2s ease;

		&:hover {
			border-color: var(--el-color-primary);
			color: var(--el-color-primary);
		}

		&.is-active {
			background: var(--el-color-primary);
			border-color: var(--el-color-primary);
			color: #fff;
			font-weight: 600;
		}

		.ratio-icon {
			display: inline-block;
			border: 1px solid currentColor;
			border-radius: 1px;
		}

		.icon-square {
			width: 8px;
			height: 8px;
		}
		.icon-landscape {
			width: 12px;
			height: 7px;
		}
		.icon-portrait {
			width: 7px;
			height: 12px;
		}
		.icon-standard-h {
			width: 10px;
			height: 7px;
		}
		.icon-standard-v {
			width: 7px;
			height: 10px;
		}
	}
}

/* 参考图片上传/输入区 */
.reference-input-area {
	.upload-wrapper {
		display: flex;
		align-items: center;
		gap: 10px;

		.upload-hint {
			font-size: 12px;
			color: var(--el-text-color-placeholder);
		}
	}

	.url-input-wrapper {
		display: flex;
		flex-direction: column;
		gap: 8px;

		.url-image-preview {
			display: flex;
			align-items: center;
			gap: 8px;

			.preview-thumb {
				width: 50px;
				height: 50px;
				border-radius: 4px;
				border: 1px solid var(--el-border-color);
			}
		}
	}
}

/* 高级选项折叠区 */
.collapse-title {
	display: flex;
	align-items: center;
	gap: 6px;
	font-weight: 600;

	.collapse-sub {
		font-size: 11px;
		color: var(--el-text-color-placeholder);
		font-weight: normal;
	}
}

.advanced-editor {
	display: flex;
	flex-direction: column;
	gap: 6px;
	padding-bottom: 8px;

	.advanced-tools {
		display: flex;
		align-items: center;
		justify-content: space-between;

		.tool-note {
			font-size: 12px;
			color: var(--el-text-color-secondary);
		}
	}

	.code-textarea {
		:deep(textarea) {
			font-family: Consolas, Monaco, monospace;
			font-size: 12px;
			background: var(--el-fill-color-light);
		}
	}
}

.field-tip {
	display: flex;
	align-items: flex-start;
	gap: 6px;
	margin-top: 8px;
	padding: 6px 10px;
	background: var(--el-fill-color-light);
	border-left: 3px solid var(--el-color-info);
	border-radius: 4px;
	font-size: 12px;
	line-height: 1.4;
	color: var(--el-text-color-secondary);

	.el-icon {
		margin-top: 1px;
		flex-shrink: 0;
	}

	&.warning {
		background: var(--el-color-warning-light-9);
		border-left-color: var(--el-color-warning);
		color: var(--el-color-warning-dark-2);

		.el-icon {
			color: var(--el-color-warning);
		}
	}
}

/* ================== 右侧画廊与结果区 ================== */
.result {
	display: flex;
	flex-direction: column;
	min-height: 0;
	height: 100%;
	background: var(--el-bg-color);
	border: 1px solid var(--el-border-color-light);
	border-radius: 8px;
	box-shadow: 0 1px 4px rgba(0, 0, 0, 0.03);
	overflow: hidden;

	&__head {
		display: flex;
		align-items: center;
		justify-content: space-between;
		padding: 12px 18px;
		background: var(--el-fill-color-blank);
		border-bottom: 1px solid var(--el-border-color-lighter);
		flex-shrink: 0;

		.result-title-group {
			display: flex;
			align-items: center;
			gap: 12px;
		}

		.title-row {
			display: flex;
			align-items: center;
			gap: 6px;

			.gallery-icon {
				font-size: 18px;
				color: var(--el-color-primary);
			}

			.title-text {
				font-size: 16px;
				font-weight: 650;
				color: var(--el-text-color-primary);
			}
		}

		.meta-row {
			display: flex;
			gap: 6px;
		}

		.result-head-actions {
			display: flex;
			align-items: center;
			gap: 10px;
		}
	}

	&__body {
		flex: 1;
		min-height: 0;
		overflow-y: auto;
		padding: 16px;

		&::-webkit-scrollbar {
			width: 6px;
		}
		&::-webkit-scrollbar-thumb {
			background: var(--el-border-color-light);
			border-radius: 3px;
		}
	}

	&__inspector {
		border-top: 1px solid var(--el-border-color-lighter);
		background: var(--el-fill-color-blank);
		flex-shrink: 0;

		:deep(.el-collapse) {
			border: none;
		}

		:deep(.el-collapse-item__header) {
			padding: 0 16px;
			height: 38px;
			font-size: 12px;
			border: none;
			background: transparent;
		}

		:deep(.el-collapse-item__content) {
			padding-bottom: 10px;
		}

		.inspector-title {
			display: flex;
			align-items: center;
			gap: 6px;
			color: var(--el-text-color-regular);
		}
	}
}

/* 画廊卡片网格 */
.gallery-grid {
	display: grid;
	grid-template-columns: repeat(auto-fill, minmax(260px, 1fr));
	gap: 16px;
}

.gallery-card {
	background: var(--el-fill-color-blank);
	border: 1px solid var(--el-border-color-lighter);
	border-radius: 8px;
	overflow: hidden;
	transition: all 0.25s ease;
	box-shadow: 0 2px 6px rgba(0, 0, 0, 0.03);

	&:hover {
		transform: translateY(-2px);
		box-shadow: 0 8px 16px rgba(0, 0, 0, 0.08);
		border-color: var(--el-color-primary-light-5);

		.image-hover-overlay {
			opacity: 1;
			transform: translateY(0);
		}
	}

	.image-wrapper {
		position: relative;
		width: 100%;
		height: 280px;
		background: var(--el-fill-color-light);
		overflow: hidden;
	}

	.gallery-image {
		width: 100%;
		height: 100%;
		display: block;
	}

	.image-loading-placeholder,
	.image-error-placeholder {
		display: flex;
		flex-direction: column;
		align-items: center;
		justify-content: center;
		gap: 6px;
		height: 100%;
		color: var(--el-text-color-placeholder);
		font-size: 12px;

		.el-icon {
			font-size: 24px;
		}
	}

	/* 悬浮操作浮层 */
	.image-hover-overlay {
		position: absolute;
		bottom: 0;
		left: 0;
		right: 0;
		padding: 10px;
		background: linear-gradient(to top, rgba(0, 0, 0, 0.75) 0%, rgba(0, 0, 0, 0) 100%);
		display: flex;
		align-items: center;
		justify-content: center;
		gap: 10px;
		opacity: 0;
		transform: translateY(6px);
		transition: all 0.25s ease;

		.action-icon-btn {
			width: 32px;
			height: 32px;
			border-radius: 50%;
			background: rgba(255, 255, 255, 0.85);
			border: none;
			color: #333;
			display: flex;
			align-items: center;
			justify-content: center;
			font-size: 15px;
			cursor: pointer;
			transition: all 0.2s ease;

			&:hover {
				background: #fff;
				color: var(--el-color-primary);
				transform: scale(1.12);
			}
		}
	}

	.card-caption {
		display: flex;
		align-items: center;
		justify-content: space-between;
		padding: 8px 12px;
		background: var(--el-fill-color-blank);
		border-top: 1px solid var(--el-border-color-lighter);
		font-size: 12px;

		.index-num {
			font-weight: 600;
			color: var(--el-text-color-primary);
		}

		.format-tag {
			font-size: 11px;
			color: var(--el-text-color-secondary);
			background: var(--el-fill-color-light);
			padding: 2px 6px;
			border-radius: 3px;
		}
	}
}

/* 生成中加载态 */
.generating-state {
	display: flex;
	flex-direction: column;
	align-items: center;
	justify-content: center;
	padding: 40px 20px;
	text-align: center;

	.pulse-loader {
		position: relative;
		width: 72px;
		height: 72px;
		display: flex;
		align-items: center;
		justify-content: center;
		margin-bottom: 16px;

		.spinner-ring {
			position: absolute;
			width: 100%;
			height: 100%;
			border: 3px solid var(--el-color-primary-light-8);
			border-top-color: var(--el-color-primary);
			border-radius: 50%;
			animation: spin 1s linear infinite;
		}

		.pulse-icon {
			font-size: 28px;
			color: var(--el-color-primary);
			animation: pulse 1.5s ease-in-out infinite;
		}
	}

	.generating-title {
		font-size: 18px;
		font-weight: 650;
		color: var(--el-text-color-primary);
		margin: 0 0 6px;
	}

	.generating-desc {
		font-size: 13px;
		color: var(--el-text-color-secondary);
		margin: 0 0 24px;
	}

	.generating-skeleton-cards {
		display: grid;
		grid-template-columns: repeat(auto-fit, minmax(240px, 280px));
		gap: 16px;
		width: 100%;
		max-width: 600px;
		justify-content: center;
	}

	.skeleton-card {
		height: 260px;
		border-radius: 8px;
		overflow: hidden;
		background: var(--el-fill-color-light);
		position: relative;

		.shimmer-block {
			width: 100%;
			height: 100%;
			background: linear-gradient(
				90deg,
				rgba(255, 255, 255, 0) 0%,
				rgba(255, 255, 255, 0.4) 50%,
				rgba(255, 255, 255, 0) 100%
			);
			animation: shimmer 1.8s infinite;
		}
	}
}

/* 空状态 */
.empty-gallery {
	display: flex;
	flex-direction: column;
	align-items: center;
	justify-content: center;
	min-height: 380px;
	text-align: center;
	padding: 40px 20px;

	.empty-graphic {
		width: 80px;
		height: 80px;
		border-radius: 50%;
		background: var(--el-fill-color-light);
		display: flex;
		align-items: center;
		justify-content: center;
		margin-bottom: 16px;

		.empty-icon {
			font-size: 36px;
			color: var(--el-text-color-placeholder);
		}
	}

	.empty-title {
		margin: 0 0 6px;
		font-size: 16px;
		font-weight: 650;
		color: var(--el-text-color-primary);
	}

	.empty-desc {
		margin: 0 0 18px;
		max-width: 380px;
		font-size: 13px;
		line-height: 1.5;
		color: var(--el-text-color-secondary);
	}
}

/* 审计元信息 */
.inspector-meta-grid {
	display: grid;
	grid-template-columns: repeat(2, 1fr);
	gap: 8px;
	padding: 8px 16px;
	background: var(--el-fill-color-light);
	border-radius: 4px;
	margin: 0 16px 8px;

	.meta-item {
		display: flex;
		align-items: center;
		gap: 8px;
		font-size: 12px;

		.meta-k {
			color: var(--el-text-color-secondary);
			min-width: 60px;
		}

		.meta-v {
			color: var(--el-text-color-primary);
			font-weight: 500;
			overflow: hidden;
			text-overflow: ellipsis;
			white-space: nowrap;
		}
	}
}

.raw-tabs {
	padding: 0 16px;

	.json-box {
		position: relative;

		.json-copy-btn {
			position: absolute;
			top: 6px;
			right: 6px;
			z-index: 2;
		}

		pre {
			max-height: 220px;
			margin: 0;
			padding: 10px 12px;
			background: var(--el-fill-color-darker);
			color: #e6e6e6;
			border-radius: 4px;
			overflow: auto;
			white-space: pre-wrap;
			word-break: break-all;
			font-size: 11px;
			font-family: Consolas, Monaco, monospace;
		}
	}
}

.task-result {
	padding: 24px;

	.task-buttons {
		display: flex;
		gap: 10px;
		justify-content: center;
	}
}

@keyframes spin {
	from {
		transform: rotate(0deg);
	}
	to {
		transform: rotate(360deg);
	}
}

@keyframes pulse {
	0%,
	100% {
		transform: scale(1);
		opacity: 1;
	}
	50% {
		transform: scale(1.15);
		opacity: 0.8;
	}
}

@keyframes shimmer {
	0% {
		transform: translateX(-100%);
	}
	100% {
		transform: translateX(100%);
	}
}

@media (max-width: 992px) {
	.ai-image-workbench {
		grid-template-columns: 1fr;
		height: auto;
		min-height: auto;
	}
	.generator {
		height: auto;
		&__body {
			overflow-y: visible;
		}
	}
	.result {
		height: auto;
		min-height: 500px;
	}
}
</style>
