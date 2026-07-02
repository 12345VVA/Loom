<template>
	<div class="ai-image-workbench">
		<section class="generator">
			<header class="generator__head">
				<div>
					<h2>{{ $t('AI 生图') }}</h2>
					<span>{{ selectedProfileSummary }}</span>
				</div>
				<el-tag :type="providerKindTag.type" effect="plain">{{
					providerKindTag.label
				}}</el-tag>
			</header>

			<div v-if="showTopNotice" class="top-notice">
				<div class="top-notice__body">
					<el-icon class="notice-icon"><bell /></el-icon>
					<span class="notice-text">
						{{
							$t(
								'提示：不同模型支持的图生图、尺寸规格和专属参数存在差异，可悬停标题旁的'
							)
						}}
						<el-icon class="inline-info-icon"><info-filled /></el-icon>
						{{ $t('图标查看具体说明。') }}
					</span>
				</div>
				<el-icon class="close-icon" @click="closeTopNotice"><close /></el-icon>
			</div>

			<div class="section">
				<div class="section__title">{{ $t('调用配置') }}</div>
				<div class="field-grid">
					<cl-select
						v-model="form.profileCode"
						:options="profileOptions"
						:placeholder="$t('默认图片配置')"
						clearable
					/>
					<el-input v-model="form.scenario" :placeholder="$t('场景')" clearable />
				</div>

				<div v-if="selectedProfile" class="profile-meta">
					<el-tag size="small">{{ selectedProfile.providerName || '-' }}</el-tag>
					<el-tag size="small" type="success">{{
						selectedProfile.modelName || selectedProfile.modelId
					}}</el-tag>
					<el-tag size="small" type="info">{{
						selectedProfile.modelType || 'image'
					}}</el-tag>
					<el-tag
						v-for="item in capabilityTags"
						:key="item"
						size="small"
						effect="plain"
						>{{ item }}</el-tag
					>
				</div>
			</div>

			<div class="section">
				<div class="section__title">{{ $t('提示词') }}</div>
				<cl-editor-markdown v-model="form.prompt" :height="260" simple />
				<div v-if="isErnieIrag && form.prompt.length > 220" class="field-tip warning mt-10">
					<el-icon><info-filled /></el-icon>
					<span>{{
						$t(
							'提示：当前为 ERNIE iRAG 检索增强生图，Prompt 长度超过限额（最大 220 字符），后端将自动截断。'
						)
					}}</span>
				</div>
				<div
					v-if="
						!isErnieIrag &&
						activeLimits.max_prompt_length &&
						form.prompt.length > activeLimits.max_prompt_length
					"
					class="field-tip warning mt-10"
				>
					<el-icon><info-filled /></el-icon>
					<span
						>{{ $t('提示：当前 Prompt 长度已超过模型推荐限制（最大') }}
						{{ activeLimits.max_prompt_length }} {{ $t('字符）。') }}</span
					>
				</div>
				<el-input
					v-if="showBailianNegativePrompt"
					v-model="form.negativePrompt"
					class="mt-10"
					type="textarea"
					:rows="3"
					:placeholder="$t('负向提示词，例如：低清晰度、畸形、文字水印')"
				/>
			</div>

			<div class="section">
				<div class="section__title">
					<span>{{ $t('参考图片 (图生图)') }}</span>
					<el-tooltip
						:content="
							$t('仅在火山方舟、阿里百炼和 OpenAI 兼容渠道等支持图生图的模型下生效。')
						"
						placement="top"
						effect="dark"
					>
						<el-icon class="title-tip-icon"><info-filled /></el-icon>
					</el-tooltip>
				</div>
				<el-radio-group v-model="imageInputMode" size="small" class="mb-10">
					<el-radio-button value="upload">{{ $t('本地上传') }}</el-radio-button>
					<el-radio-button value="url">{{ $t('网络地址') }}</el-radio-button>
				</el-radio-group>

				<div v-if="imageInputMode === 'upload'" class="mt-10">
					<cl-upload v-model="form.image" :limit="1" />
				</div>
				<div v-else class="mt-10">
					<el-input
						v-model="form.image"
						:placeholder="$t('请输入参考图片 URL')"
						clearable
					/>
				</div>

				<div class="field-tip">
					<el-icon><info-filled /></el-icon>
					<span>{{
						$t('仅在火山方舟、阿里百炼和 OpenAI 兼容渠道等支持图生图的模型下生效。')
					}}</span>
				</div>
			</div>

			<div class="section">
				<div class="section__title">
					<span>{{ $t('通用参数') }}</span>
					<el-tooltip v-if="sizeHint" :content="sizeHint" placement="top" effect="dark">
						<el-icon class="title-tip-icon"><info-filled /></el-icon>
					</el-tooltip>
				</div>
				<div class="field-grid field-grid--compact">
					<el-form-item :label="$t('尺寸')">
						<cl-select v-model="form.size" :options="availableSizeOptions" />
					</el-form-item>
					<el-form-item :label="$t('数量')">
						<el-input-number
							v-model="form.n"
							:min="1"
							:max="activeLimits.max_n || 8"
							controls-position="right"
						/>
					</el-form-item>
					<el-form-item :label="$t('返回')">
						<cl-select v-model="form.responseFormat" :options="responseFormatOptions" />
					</el-form-item>
					<el-form-item v-if="showWatermarkOption" :label="$t('水印')">
						<el-switch v-model="form.watermark" />
					</el-form-item>
				</div>
			</div>

			<div class="section">
				<div class="section__title">
					<span>{{ $t('厂商参数') }}</span>
					<el-tooltip :content="providerHint" placement="top" effect="dark">
						<el-icon class="title-tip-icon"><info-filled /></el-icon>
					</el-tooltip>
				</div>
				<div v-if="providerKind === 'bailian'" class="provider-panel">
					<el-checkbox v-model="form.promptExtend">{{
						$t('智能改写 prompt_extend')
					}}</el-checkbox>
					<el-checkbox v-model="form.forceAsync">{{ $t('强制异步') }}</el-checkbox>
				</div>

				<div v-else-if="providerKind === 'volcengine-ark'" class="provider-panel">
					<div class="field-grid field-grid--vertical">
						<el-form-item>
							<template #label>
								<span class="mr-4">guidance_scale</span>
								<el-tooltip
									:content="
										$t(
											'分类指导比例。值越大越贴近提示词，但过大可能导致画面发硬或色彩过饱和，推荐 5.0 - 10.0。'
										)
									"
									placement="top"
								>
									<el-icon class="label-tip-icon"><info-filled /></el-icon>
								</el-tooltip>
							</template>
							<el-input-number
								v-model="form.guidanceScale"
								:min="0"
								:max="20"
								:step="0.5"
								controls-position="right"
							/>
						</el-form-item>
						<el-form-item>
							<template #label>
								<span class="mr-4">sequential_image_generation</span>
								<el-tooltip
									:content="
										$t(
											'多图生成调度模式。disabled 表示并行生成；auto 表示自动调度，在生成大图或资源紧张时可提高成功率。'
										)
									"
									placement="top"
								>
									<el-icon class="label-tip-icon"><info-filled /></el-icon>
								</el-tooltip>
							</template>
							<cl-select
								v-model="form.sequentialImageGeneration"
								:options="sequentialOptions"
								clearable
							/>
						</el-form-item>
					</div>
				</div>

				<div v-else-if="providerKind === 'openai'" class="provider-panel">
					<div class="field-grid">
						<el-form-item label="quality">
							<cl-select v-model="form.quality" :options="qualityOptions" clearable />
						</el-form-item>
						<el-form-item label="style">
							<cl-select v-model="form.style" :options="styleOptions" clearable />
						</el-form-item>
						<el-form-item :label="$t('思维思考')">
							<el-switch v-model="form.thinking" />
						</el-form-item>
					</div>
				</div>

				<div v-else-if="providerKind === 'qianfan'" class="provider-panel">
					<div class="field-tip">
						<el-icon><info-filled /></el-icon>
						<span>{{
							isErnieIrag
								? $t(
										'当前使用百度 ERNIE iRAG 检索增强模型。中文文本准确度高，支持参考图，Prompt 限制 220 字符；不支持负向提示词与随机种子。'
									)
								: $t(
										'当前使用百度千帆 V2 接口。支持负向提示词与随机种子（可在高级 JSON 设置）。'
									)
						}}</span>
					</div>
				</div>

				<div v-else-if="providerKind === 'gemini'" class="provider-panel">
					<div class="field-tip">
						<el-icon><info-filled /></el-icon>
						<span>{{
							$t(
								'当前使用谷歌 Gemini 原生生图，已平滑支持 gemini-2.5-flash-image 替代 Imagen。支持参考图，可结合 text/image 多模态调用。'
							)
						}}</span>
					</div>
				</div>

				<div v-else class="field-tip warning">
					<el-icon><info-filled /></el-icon>
					<span>{{ $t('该厂商暂未配置专属参数，可使用通用参数和高级 JSON。') }}</span>
				</div>
			</div>

			<div class="section">
				<el-collapse>
					<el-collapse-item :title="$t('高级参数 JSON')" name="advanced">
						<div class="advanced__head">
							<span>{{ $t('高级参数会最后合并，可覆盖表单参数') }}</span>
							<el-button text type="primary" @click="resetOptions">{{
								$t('重置')
							}}</el-button>
						</div>
						<el-input v-model="form.optionsText" type="textarea" :rows="8" />
					</el-collapse-item>
				</el-collapse>
			</div>

			<footer class="actions">
				<el-button @click="clearResult">{{ $t('清空结果') }}</el-button>
				<el-button :loading="loading.submit" type="warning" @click="submitTask">{{
					$t('异步提交')
				}}</el-button>
				<el-button :loading="loading.generate" type="primary" @click="generate">{{
					$t('生成图片')
				}}</el-button>
			</footer>
		</section>

		<aside class="result">
			<header>
				<div>
					<strong>{{ $t('生成结果') }}</strong>
					<span v-if="resultMeta.length">{{ resultMeta.join(' / ') }}</span>
				</div>
				<el-tag v-if="imageItems.length" size="small" type="success">{{
					imageItems.length
				}}</el-tag>
			</header>

			<div v-if="taskSubmitted" class="task-result">
				<el-result
					icon="success"
					:title="$t('任务已提交')"
					:sub-title="`Task ID: ${taskSubmitted.taskId}`"
				>
					<template #extra>
						<el-button type="primary" @click="copyText(String(taskSubmitted.taskId))">{{
							$t('复制任务 ID')
						}}</el-button>
					</template>
				</el-result>
			</div>

			<div v-else class="preview-list">
				<div v-for="(item, index) in imageItems" :key="index" class="preview-item">
					<el-image
						class="preview-image"
						:src="item.src"
						fit="contain"
						:preview-src-list="previewUrls"
						:initial-index="index"
						preview-teleported
					/>
					<div class="preview-actions">
						<el-button text type="primary" @click="copyText(item.value)">{{
							$t('复制')
						}}</el-button>
						<el-button v-if="item.url" text type="primary" @click="openUrl(item.url)">{{
							$t('打开')
						}}</el-button>
					</div>
				</div>
				<el-empty v-if="!imageItems.length" :description="$t('暂无图片')" />
			</div>

			<el-descriptions v-if="result" class="result-meta" border :column="2">
				<el-descriptions-item label="Provider">{{
					result.provider || '-'
				}}</el-descriptions-item>
				<el-descriptions-item label="Model">{{ result.model || '-' }}</el-descriptions-item>
				<el-descriptions-item label="Profile">{{
					result.profile || '-'
				}}</el-descriptions-item>
				<el-descriptions-item label="Request ID">{{
					result.requestId || result.taskId || '-'
				}}</el-descriptions-item>
			</el-descriptions>

			<el-tabs class="raw-tabs">
				<el-tab-pane :label="$t('请求')">
					<pre>{{ formatJson(lastPayload) }}</pre>
				</el-tab-pane>
				<el-tab-pane :label="$t('响应')">
					<pre>{{ formatJson(result) }}</pre>
				</el-tab-pane>
			</el-tabs>
		</aside>
	</div>
</template>

<script lang="ts" setup>
defineOptions({
	name: 'ai-image'
});

import { computed, onMounted, reactive, ref, watch } from 'vue';
import { ElMessage } from 'element-plus';
import { useCool } from '/@/cool';
import { useI18n } from 'vue-i18n';
import { Bell, Close, InfoFilled } from '@element-plus/icons-vue';
import { findImageData } from './image-utils';

const { service } = useCool();
const { t } = useI18n();
const aiService = service.ai as any;

const showTopNotice = ref(localStorage.getItem('loom_ai_image_notice_closed') !== 'true');

function closeTopNotice() {
	showTopNotice.value = false;
	localStorage.setItem('loom_ai_image_notice_closed', 'true');
}

const imageInputMode = ref('upload');

watch(imageInputMode, () => {
	if (typeof form.image !== 'string') {
		form.image = '';
	}
});

const profiles = ref<any[]>([]);
const result = ref<any>(null);
const lastPayload = ref<any>(null);
const loading = reactive({
	generate: false,
	submit: false
});
const form = reactive({
	profileCode: '',
	scenario: 'default',
	prompt: '一张未来感 AI 内容平台海报，干净的构图，科技感灯光，高质量细节',
	negativePrompt: '',
	image: '',
	size: '2560x1440',
	n: 1,
	responseFormat: 'url',
	watermark: true,
	promptExtend: false,
	forceAsync: false,
	guidanceScale: undefined as number | undefined,
	sequentialImageGeneration: '',
	quality: '',
	style: '',
	thinking: false,
	optionsText: '{}'
});

const sizeOptions = [
	{ label: '1024x1024', value: '1024x1024' },
	{ label: '2048x2048', value: '2048x2048' },
	{ label: '2304x1728', value: '2304x1728' },
	{ label: '1728x2304', value: '1728x2304' },
	{ label: '2560x1440', value: '2560x1440' },
	{ label: '1440x2560', value: '1440x2560' },
	{ label: '2496x1664', value: '2496x1664' },
	{ label: '1664x2496', value: '1664x2496' }
];
const openaiAutoSizeOption = { label: '自动比例（仅 OpenAI 官方）', value: 'auto' };
const bailianSizeOptions = [
	{ label: '1024x1024（1:1）', value: '1024x1024' },
	{ label: '768x1024（3:4）', value: '768x1024' },
	{ label: '1024x768（4:3）', value: '1024x768' },
	{ label: '720x1280（9:16）', value: '720x1280' },
	{ label: '1280x720（16:9）', value: '1280x720' }
];
const volcengineSeedream4SizeOptions = [
	{ label: '2560x1440（16:9）', value: '2560x1440' },
	{ label: '1440x2560（9:16）', value: '1440x2560' },
	{ label: '2048x2048（1:1）', value: '2048x2048' }
];
const volcengineSizeOptions = [
	{ label: '1024x1024（1:1）', value: '1024x1024' },
	{ label: '1024x1536（2:3）', value: '1024x1536' },
	{ label: '1536x1024（3:2）', value: '1536x1024' },
	{ label: '864x1152（3:4）', value: '864x1152' },
	{ label: '1152x864（4:3）', value: '1152x864' },
	{ label: '768x1344（9:16）', value: '768x1344' },
	{ label: '1344x768（16:9）', value: '1344x768' }
];
const responseFormatOptions = [
	{ label: 'url', value: 'url' },
	{ label: 'b64_json', value: 'b64_json' }
];
const sequentialOptions = [
	{ label: 'disabled', value: 'disabled' },
	{ label: 'auto', value: 'auto' }
];
const qualityOptions = [
	{ label: 'standard', value: 'standard' },
	{ label: 'hd', value: 'hd' }
];
const styleOptions = [
	{ label: 'vivid', value: 'vivid' },
	{ label: 'natural', value: 'natural' }
];

const selectedProfile = computed(() => profiles.value.find(item => item.code === form.profileCode));
const selectedProfileSummary = computed(() => {
	const item = selectedProfile.value;
	if (!item) {
		return t('未选择时使用默认 image Profile');
	}
	return `${item.name || item.code} / ${item.modelName || item.modelId} / ${item.providerName || '-'}`;
});
const profileOptions = computed(() =>
	profiles.value.map((item: any) => ({
		label: `${item.name || item.code} / ${item.modelName || item.modelId} / ${item.providerName || '-'}`,
		value: item.code
	}))
);
const providerKind = computed(() => detectProviderKind(selectedProfile.value));
const bailianModelCode = computed(() =>
	String(selectedProfile.value?.modelCode || selectedProfile.value?.modelName || '').toLowerCase()
);
const selectedModelCode = computed(() =>
	String(selectedProfile.value?.modelCode || selectedProfile.value?.modelName || '')
		.toLowerCase()
		.replace(/\./g, '-')
);
const isBailianWan26 = computed(() =>
	bailianModelCode.value.replace(/_/g, '-').startsWith('wan2.6-')
);
const isVolcengineSeedream4 = computed(
	() =>
		providerKind.value === 'volcengine-ark' &&
		(selectedModelCode.value.includes('seedream-4-5') ||
			selectedModelCode.value.includes('seedream-4-0'))
);
const showBailianNegativePrompt = computed(
	() => providerKind.value === 'bailian' && (!isBailianWan26.value || form.forceAsync)
);
const showWatermarkOption = computed(() => providerKind.value !== 'openai');
const availableSizeOptions = computed(() => {
	const profile = selectedProfile.value;
	if (profile && profile.modelDefaultConfig) {
		try {
			const config = JSON.parse(profile.modelDefaultConfig);
			if (config && Array.isArray(config._sizes)) {
				return config._sizes;
			}
		} catch (e) {
			console.warn('解析模型默认尺寸选项失败:', e);
		}
	}
	if (providerKind.value === 'openai') {
		return [openaiAutoSizeOption, ...sizeOptions];
	}
	if (providerKind.value === 'bailian') {
		return bailianSizeOptions;
	}
	if (providerKind.value === 'volcengine-ark') {
		if (isVolcengineSeedream4.value) {
			return volcengineSeedream4SizeOptions;
		}
		return volcengineSizeOptions;
	}
	return sizeOptions;
});

const activeLimits = computed(() => {
	const profile = selectedProfile.value;
	if (profile && profile.modelDefaultConfig) {
		try {
			const config = JSON.parse(profile.modelDefaultConfig);
			if (config && config._limits) {
				return {
					max_n: config._limits.max_n || 8,
					max_prompt_length: config._limits.max_prompt_length
				};
			}
		} catch (e) {}
	}
	return { max_n: 8 };
});
const sizeHint = computed(() => {
	if (providerKind.value === 'openai') {
		return t(
			'OpenAI 官方图片接口支持 size=auto；OpenAI 兼容渠道不保证所有底层模型都支持自动比例。'
		);
	}
	if (providerKind.value === 'bailian') {
		return t('阿里百炼当前按显式尺寸/固定比例使用，未开放自动比例。');
	}
	if (providerKind.value === 'volcengine-ark') {
		if (isVolcengineSeedream4.value) {
			return t('火山 Seedream 4.x 至少需要 3686400 像素，仅可使用高分辨率尺寸。');
		}
		return t(
			'火山方舟当前按固定尺寸/比例使用，sequential_image_generation 的 auto 不是图片比例自动。'
		);
	}
	return t('当前渠道建议使用显式尺寸，若需特殊比例请结合模型文档确认。');
});
const providerKindTag = computed(() => {
	const map: Record<string, any> = {
		bailian: { label: '阿里百炼', type: 'success' },
		'volcengine-ark': { label: '火山方舟', type: 'warning' },
		openai: { label: 'OpenAI Compatible', type: 'primary' },
		qianfan: { label: '百度千帆', type: 'success' },
		gemini: { label: '谷歌 Gemini', type: 'danger' },
		unknown: { label: t('通用'), type: 'info' }
	};
	return map[providerKind.value] || map.unknown;
});

const providerHint = computed(() => {
	if (providerKind.value === 'bailian') {
		return t(
			'百炼 workspace、轮询间隔等在厂商扩展配置中设置；这里的异步开关会写入 options.async。'
		);
	}
	if (providerKind.value === 'volcengine-ark') {
		return t('Seedream 4.x 图片尺寸要求较高；后端会继续做最终校验。');
	}
	if (providerKind.value === 'openai') {
		return t('支持配置 OpenAI 专属的生图品质 quality、风格 style 以及 thinking 思维参数。');
	}
	if (providerKind.value === 'qianfan') {
		return t('支持百度智能云千帆大模型 V2 生图参数适配，包含 ERNIE iRAG 检索增强防超长机制。');
	}
	if (providerKind.value === 'gemini') {
		return t('已接入谷歌 Gemini 原生 generateContent 生图，自动兼容处理参考图。');
	}
	return t('该厂商暂未配置专属参数，可使用通用参数和高级 JSON。');
});
const capabilityTags = computed(() =>
	String(selectedProfile.value?.modelCapabilities || selectedProfile.value?.capabilities || '')
		.split(',')
		.map(item => item.trim())
		.filter(Boolean)
);
const imageItems = computed(() => extractImageItems(result.value));
const previewUrls = computed(() => imageItems.value.map(item => item.src));
const taskSubmitted = computed(() => {
	if (result.value?.taskId && !imageItems.value.length) {
		return result.value;
	}
	return null;
});
const resultMeta = computed(() =>
	[result.value?.provider, result.value?.model, result.value?.profile].filter(Boolean)
);

onMounted(() => {
	loadProfiles();
});

watch(
	[providerKind, isVolcengineSeedream4, availableSizeOptions],
	([kind, isSeedream4, options]) => {
		if (kind !== 'volcengine-ark' || !isSeedream4) {
			return;
		}
		if (!options.some(item => item.value === form.size)) {
			form.size = options[0]?.value || '2560x1440';
		}
	},
	{ immediate: true }
);

watch(selectedProfile, profile => {
	if (profile && profile.modelDefaultConfig) {
		try {
			const config = JSON.parse(profile.modelDefaultConfig);
			if (config) {
				if (
					config.size &&
					availableSizeOptions.value.some(item => item.value === config.size)
				) {
					form.size = config.size;
				} else if (availableSizeOptions.value.length > 0) {
					form.size = availableSizeOptions.value[0].value;
				}
				if (config.n !== undefined) {
					form.n = Math.min(config.n, activeLimits.value.max_n || 8);
				}
				if (config.response_format) {
					form.responseFormat = config.response_format;
				}
				if (config.watermark !== undefined) {
					form.watermark = config.watermark;
				}
				if (config.quality) {
					form.quality = config.quality;
				}
				if (config.style) {
					form.style = config.style;
				}
				if (config.thinking !== undefined) {
					form.thinking = config.thinking;
				}
			}
		} catch (e) {
			console.warn('自动加载模型默认参数失败:', e);
		}
	}
});

async function loadProfiles() {
	const res = await (service.ai.profile as any).list({
		modelType: 'image',
		status: true
	});
	profiles.value = res || [];
}

function buildPayload() {
	const prompt = form.prompt.trim();
	if (!prompt) {
		ElMessage.warning(t('请输入提示词'));
		return null;
	}

	let advanced: Record<string, any> = {};
	try {
		advanced = form.optionsText.trim() ? JSON.parse(form.optionsText) : {};
	} catch (err: any) {
		ElMessage.error(`${t('高级参数 JSON 格式错误')}: ${err.message}`);
		return null;
	}

	return {
		scenario: form.scenario || 'default',
		profileCode: form.profileCode || undefined,
		prompt,
		image: form.image.trim() || undefined,
		options: {
			...baseOptions(),
			...providerOptions(),
			...advanced
		}
	};
}

function baseOptions() {
	const options: Record<string, any> = {
		size: form.size,
		n: form.n,
		response_format: form.responseFormat
	};
	if (showWatermarkOption.value) {
		options.watermark = form.watermark;
	}
	return cleanOptions(options);
}

function providerOptions() {
	const options: Record<string, any> = {};
	if (providerKind.value === 'bailian') {
		if (showBailianNegativePrompt.value) {
			options.negative_prompt = form.negativePrompt.trim() || undefined;
		}
		options.prompt_extend = form.promptExtend || undefined;
		options.async = form.forceAsync || undefined;
	}
	if (providerKind.value === 'volcengine-ark') {
		options.guidance_scale = form.guidanceScale;
		options.sequential_image_generation = form.sequentialImageGeneration || undefined;
	}
	if (providerKind.value === 'openai') {
		options.quality = form.quality || undefined;
		options.style = form.style || undefined;
		options.thinking = form.thinking || undefined;
	}
	return cleanOptions(options);
}

function cleanOptions(value: Record<string, any>) {
	return Object.fromEntries(
		Object.entries(value).filter(([, item]) => item !== undefined && item !== '')
	);
}

async function generate() {
	const payload = buildPayload();
	if (!payload) {
		return;
	}

	loading.generate = true;
	lastPayload.value = payload;
	try {
		result.value = await aiService.runtime.model.image(payload);
		if (!extractImageItems(result.value).length) {
			ElMessage.warning(t('调用成功，但未解析到图片'));
		}
	} catch (err: any) {
		ElMessage.error(err.message || t('生成失败'));
	} finally {
		loading.generate = false;
	}
}

async function submitTask() {
	const payload = buildPayload();
	if (!payload) {
		return;
	}

	loading.submit = true;
	lastPayload.value = {
		taskType: 'image',
		scenario: payload.scenario,
		profileCode: payload.profileCode,
		payload: {
			prompt: payload.prompt,
			image: payload.image,
			options: payload.options
		}
	};
	try {
		result.value = await aiService.runtime.model.submitTask(lastPayload.value);
		ElMessage.success(t('提交成功'));
	} catch (err: any) {
		ElMessage.error(err.message || t('提交失败'));
	} finally {
		loading.submit = false;
	}
}

function resetOptions() {
	form.optionsText = '{}';
}

function clearResult() {
	result.value = null;
	lastPayload.value = null;
}

async function copyText(value: string) {
	await navigator.clipboard.writeText(value);
	ElMessage.success(t('已复制'));
}

function openUrl(url: string) {
	window.open(url, '_blank');
}

function formatJson(value: any) {
	if (!value) {
		return '-';
	}
	return JSON.stringify(value, null, 2);
}

const isErnieIrag = computed(() => {
	const code = String(
		selectedProfile.value?.modelCode || selectedProfile.value?.modelName || ''
	).toLowerCase();
	return code.includes('irag-1.0') || code.includes('irag-1-0') || code.includes('ernie-irag');
});

function detectProviderKind(profile: any) {
	const adapter = normalizeProviderToken(profile?.providerAdapter || profile?.adapter);
	const providerCode = normalizeProviderToken(profile?.providerCode);
	const modelCode = normalizeProviderToken(profile?.modelCode);
	const capabilities = normalizeProviderToken(
		profile?.modelCapabilities || profile?.capabilities
	);
	const fallback = normalizeProviderToken(
		`${profile?.providerName || ''} ${profile?.modelName || ''}`
	);

	if (
		adapter === 'bailian' ||
		providerCode === 'bailian' ||
		modelCode.includes('wan2.') ||
		modelCode.includes('wanx')
	) {
		return 'bailian';
	}
	if (
		adapter === 'volcengine-ark' ||
		providerCode.includes('volcengine') ||
		modelCode.includes('seedream') ||
		modelCode.includes('doubao')
	) {
		return 'volcengine-ark';
	}
	if (
		adapter === 'openai-compatible' ||
		providerCode.includes('openai') ||
		capabilities.includes('openai')
	) {
		return 'openai';
	}
	if (
		adapter === 'qianfan' ||
		providerCode.includes('qianfan') ||
		modelCode.includes('ernie') ||
		modelCode.startsWith('irag') ||
		modelCode.includes('-irag')
	) {
		return 'qianfan';
	}
	if (adapter === 'gemini' || providerCode.includes('gemini') || modelCode.includes('gemini')) {
		return 'gemini';
	}
	if (
		fallback.includes('bailian') ||
		fallback.includes('百炼') ||
		fallback.includes('wan2.') ||
		fallback.includes('wanx')
	) {
		return 'bailian';
	}
	if (
		fallback.includes('volcengine') ||
		fallback.includes('火山') ||
		fallback.includes('seedream') ||
		fallback.includes('doubao')
	) {
		return 'volcengine-ark';
	}
	if (fallback.includes('qianfan') || fallback.includes('千帆')) {
		return 'qianfan';
	}
	if (fallback.includes('gemini') || fallback.includes('谷歌')) {
		return 'gemini';
	}
	if (fallback.includes('openai')) {
		return 'openai';
	}
	return 'unknown';
}

function normalizeProviderToken(value: any) {
	return String(value || '')
		.trim()
		.toLowerCase();
}

function extractImageItems(value: any): { src: string; value: string; url?: string }[] {
	const items = findImageData(value);
	return items
		.map(item => {
			const url = item?.url || item?.image_url || item?.imageUrl || item?.image;
			const b64 = item?.b64_json || item?.b64Json || item?.base64;
			if (url) {
				return { src: url, value: url, url };
			}
			if (b64) {
				const src = String(b64).startsWith('data:image')
					? String(b64)
					: `data:image/png;base64,${b64}`;
				return { src, value: String(b64) };
			}
			return null;
		})
		.filter(Boolean) as { src: string; value: string; url?: string }[];
}

// findImageData 已抽离至 ./image-utils，便于单元测试（含递归深度保护）
</script>

<style lang="scss" scoped>
.ai-image-workbench {
	display: grid;
	grid-template-columns: minmax(360px, 460px) minmax(0, 1fr);
	gap: 12px;
	height: 100%;
	min-height: 720px;
}

.generator,
.result {
	display: flex;
	min-height: 0;
	border: 1px solid var(--el-border-color-light);
	background: var(--el-bg-color);
}

.generator {
	flex-direction: column;
	overflow: auto;

	&__head {
		display: flex;
		align-items: center;
		justify-content: space-between;
		gap: 12px;
		padding: 14px;
		border-bottom: 1px solid var(--el-border-color-light);

		h2 {
			margin: 0 0 4px;
			font-size: 18px;
			font-weight: 650;
		}

		span {
			color: var(--el-text-color-secondary);
			font-size: 13px;
		}
	}
}

.section {
	padding: 12px 14px;
	border-bottom: 1px solid var(--el-border-color-lighter);

	&__title {
		display: flex;
		align-items: center;
		gap: 6px;
		margin-bottom: 10px;
		font-weight: 650;

		.title-tip-icon {
			font-size: 14px;
			color: var(--el-text-color-placeholder);
			cursor: pointer;
			transition: color 0.3s;

			&:hover {
				color: var(--el-color-primary);
			}
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
		grid-template-columns: repeat(2, minmax(0, 1fr));
	}

	&--vertical {
		grid-template-columns: 1fr;
	}
}

.profile-meta {
	display: flex;
	flex-wrap: wrap;
	gap: 6px;
	margin-top: 10px;
}

.provider-panel {
	:deep(.el-checkbox) {
		margin-right: 16px;
	}

	.label-tip-icon {
		margin-left: 4px;
		font-size: 14px;
		color: var(--el-text-color-placeholder);
		cursor: pointer;
		vertical-align: middle;
		transition: color 0.3s;

		&:hover {
			color: var(--el-color-primary);
		}
	}
}

.advanced__head {
	display: flex;
	align-items: center;
	justify-content: space-between;
	margin-bottom: 8px;
	color: var(--el-text-color-secondary);
	font-size: 13px;
}

.mt-10 {
	margin-top: 10px;
}

.mb-10 {
	margin-bottom: 10px;
}

.actions {
	display: flex;
	justify-content: flex-end;
	gap: 8px;
	padding: 12px 14px;
	margin-top: auto;
	border-top: 1px solid var(--el-border-color-light);
}

.result {
	flex-direction: column;

	header {
		display: flex;
		align-items: center;
		justify-content: space-between;
		gap: 12px;
		padding: 12px;
		border-bottom: 1px solid var(--el-border-color-light);

		div {
			display: grid;
			gap: 4px;
		}

		span {
			color: var(--el-text-color-secondary);
			font-size: 13px;
		}
	}
}

.task-result {
	padding: 18px;
}

.preview-list {
	display: grid;
	grid-template-columns: repeat(auto-fill, minmax(220px, 1fr));
	gap: 12px;
	min-height: 280px;
	max-height: 48vh;
	overflow: auto;
	padding: 12px;
}

.preview-item {
	border: 1px solid var(--el-border-color-lighter);
	border-radius: 6px;
	background: var(--el-fill-color-blank);
}

.preview-image {
	display: block;
	width: 100%;
	height: 220px;
	background: var(--el-fill-color-lighter);
}

.preview-actions {
	display: flex;
	justify-content: flex-end;
	gap: 8px;
	padding: 8px;
}

.result-meta {
	margin: 0 12px 12px;
}

.raw-tabs {
	min-height: 0;
	padding: 0 12px 12px;

	pre {
		max-height: 260px;
		margin: 0;
		overflow: auto;
		white-space: pre-wrap;
		word-break: break-word;
		font-size: 12px;
	}
}

@media (max-width: 960px) {
	.ai-image-workbench {
		grid-template-columns: 1fr;
		height: auto;
	}
}

/* 顶部统一提示栏样式 */
.top-notice {
	display: flex;
	align-items: flex-start;
	justify-content: space-between;
	gap: 12px;
	margin: 10px 14px 2px;
	padding: 10px 12px;
	background: var(--el-color-primary-light-9);
	border: 1px solid var(--el-color-primary-light-8);
	border-radius: 6px;
	transition: all 0.3s ease;

	&__body {
		display: flex;
		align-items: flex-start;
		gap: 8px;
		color: var(--el-color-primary);
		font-size: 12px;
		line-height: 1.5;

		.notice-icon {
			font-size: 16px;
			margin-top: 1px;
			flex-shrink: 0;
		}

		.inline-info-icon {
			font-size: 13px;
			vertical-align: middle;
			margin: 0 2px;
			color: var(--el-color-primary);
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

/* 局部内联精致提示 */
.field-tip {
	display: flex;
	align-items: flex-start;
	gap: 6px;
	margin-top: 10px;
	padding: 8px 10px;
	background: var(--el-fill-color-lighter);
	border-left: 3px solid var(--el-color-info);
	border-radius: 4px;
	color: var(--el-text-color-secondary);
	font-size: 12px;
	line-height: 1.4;

	.el-icon {
		color: var(--el-text-color-placeholder);
		font-size: 14px;
		margin-top: 1px;
		flex-shrink: 0;
	}

	&.warning {
		background: var(--el-color-warning-light-9);
		border-left-color: var(--el-color-warning);
		color: var(--el-color-warning-active);

		.el-icon {
			color: var(--el-color-warning);
		}
	}
}
</style>
