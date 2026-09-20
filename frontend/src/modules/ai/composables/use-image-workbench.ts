/**
 * 生图工作台状态：表单、派生态与动作。
 * 从 image.vue 抽出，视图只负责模板组合与结果区交互。
 */
import { computed, onMounted, reactive, ref, watch } from 'vue';
import { ElMessage } from 'element-plus';
import { useCool } from '/@/cool';
import { useI18n } from 'vue-i18n';
import { extractImageItems } from '../utils/image-utils';
import {
	BAILIAN_SIZE_OPTIONS,
	BASE_SIZE_OPTIONS,
	OPENAI_AUTO_SIZE_OPTION,
	VOLCENGINE_SEEDREAM4_SIZE_OPTIONS,
	VOLCENGINE_SIZE_OPTIONS,
	detectProviderKind,
	parseProfileLimits,
	parseProfileSizeOptions,
	type ImageProfileLimits,
	type ImageProviderKind,
	type ImageSizeOption
} from '../utils/image-providers';
import { aiRuntime } from '../service';

export interface ImageWorkbenchForm {
	profileCode: string;
	scenario: string;
	prompt: string;
	negativePrompt: string;
	image: string;
	size: string;
	n: number;
	responseFormat: string;
	watermark: boolean;
	promptExtend: boolean;
	forceAsync: boolean;
	guidanceScale: number | undefined;
	sequentialImageGeneration: string;
	quality: string;
	style: string;
	thinking: boolean;
	optionsText: string;
}

export function useImageWorkbench() {
	const { service } = useCool();
	const { t } = useI18n();

	const profiles = ref<any[]>([]);
	const result = ref<any>(null);
	const lastPayload = ref<any>(null);
	const loading = reactive({
		generate: false,
		submit: false
	});
	const form = reactive<ImageWorkbenchForm>({
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
		guidanceScale: undefined,
		sequentialImageGeneration: '',
		quality: '',
		style: '',
		thinking: false,
		optionsText: '{}'
	});

	const selectedProfile = computed(() =>
		profiles.value.find(item => item.code === form.profileCode)
	);
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
	const providerKind = computed<ImageProviderKind>(() => detectProviderKind(selectedProfile.value));
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
	const availableSizeOptions = computed<ImageSizeOption[]>(() => {
		const declared = parseProfileSizeOptions(selectedProfile.value?.modelDefaultConfig);
		if (declared) {
			return declared;
		}
		if (providerKind.value === 'openai') {
			return [OPENAI_AUTO_SIZE_OPTION, ...BASE_SIZE_OPTIONS];
		}
		if (providerKind.value === 'bailian') {
			return BAILIAN_SIZE_OPTIONS;
		}
		if (providerKind.value === 'volcengine-ark') {
			if (isVolcengineSeedream4.value) {
				return VOLCENGINE_SEEDREAM4_SIZE_OPTIONS;
			}
			return VOLCENGINE_SIZE_OPTIONS;
		}
		return BASE_SIZE_OPTIONS;
	});

	const activeLimits = computed<ImageProfileLimits>(() =>
		parseProfileLimits(selectedProfile.value?.modelDefaultConfig)
	);
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
	const isErnieIrag = computed(() => {
		const code = String(
			selectedProfile.value?.modelCode || selectedProfile.value?.modelName || ''
		).toLowerCase();
		return code.includes('irag-1.0') || code.includes('irag-1-0') || code.includes('ernie-irag');
	});

	// Seedream 4.x 切换后当前尺寸可能不再合法，回退到首个可用尺寸
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

	// 选择配置后应用模型默认参数
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

	onMounted(() => {
		loadProfiles();
	});

	async function loadProfiles() {
		// EPS 生成的 list 参数类型未含业务查询字段，实际后端支持，此处对参数放宽类型
		const res = await service.ai.profile.list({
			modelType: 'image',
			status: true
		} as any);
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
			result.value = await aiRuntime.image(payload);
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
			result.value = await service.ai.task.submit(lastPayload.value);
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

	return {
		// 状态
		profiles,
		result,
		lastPayload,
		loading,
		form,
		// 派生态
		selectedProfile,
		selectedProfileSummary,
		profileOptions,
		providerKind,
		isBailianWan26,
		isVolcengineSeedream4,
		showBailianNegativePrompt,
		showWatermarkOption,
		availableSizeOptions,
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
		// 动作
		loadProfiles,
		generate,
		submitTask,
		resetOptions,
		clearResult
	};
}
