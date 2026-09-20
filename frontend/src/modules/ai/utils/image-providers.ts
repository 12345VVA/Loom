/**
 * 生图厂商识别与渠道参数常量。
 * 从 image.vue 抽出：本文件只包含纯数据与纯函数，便于单元测试；
 * 依赖 i18n 的提示文案留在 composables/use-image-workbench 中。
 */

export type ImageProviderKind =
	| 'bailian'
	| 'volcengine-ark'
	| 'openai'
	| 'qianfan'
	| 'gemini'
	| 'unknown';

export interface ImageSizeOption {
	label: string;
	value: string;
}

export interface ImageProfileLimits {
	max_n: number;
	max_prompt_length?: number;
}

export function normalizeProviderToken(value: any): string {
	return String(value || '')
		.trim()
		.toLowerCase();
}

export function detectProviderKind(profile: any): ImageProviderKind {
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

export const BASE_SIZE_OPTIONS: ImageSizeOption[] = [
	{ label: '1024x1024', value: '1024x1024' },
	{ label: '2048x2048', value: '2048x2048' },
	{ label: '2304x1728', value: '2304x1728' },
	{ label: '1728x2304', value: '1728x2304' },
	{ label: '2560x1440', value: '2560x1440' },
	{ label: '1440x2560', value: '1440x2560' },
	{ label: '2496x1664', value: '2496x1664' },
	{ label: '1664x2496', value: '1664x2496' }
];

export const OPENAI_AUTO_SIZE_OPTION: ImageSizeOption = {
	label: '自动比例（仅 OpenAI 官方）',
	value: 'auto'
};

export const BAILIAN_SIZE_OPTIONS: ImageSizeOption[] = [
	{ label: '1024x1024（1:1）', value: '1024x1024' },
	{ label: '768x1024（3:4）', value: '768x1024' },
	{ label: '1024x768（4:3）', value: '1024x768' },
	{ label: '720x1280（9:16）', value: '720x1280' },
	{ label: '1280x720（16:9）', value: '1280x720' }
];

export const VOLCENGINE_SEEDREAM4_SIZE_OPTIONS: ImageSizeOption[] = [
	{ label: '2560x1440（16:9）', value: '2560x1440' },
	{ label: '1440x2560（9:16）', value: '1440x2560' },
	{ label: '2048x2048（1:1）', value: '2048x2048' }
];

export const VOLCENGINE_SIZE_OPTIONS: ImageSizeOption[] = [
	{ label: '1024x1024（1:1）', value: '1024x1024' },
	{ label: '1024x1536（2:3）', value: '1024x1536' },
	{ label: '1536x1024（3:2）', value: '1536x1024' },
	{ label: '864x1152（3:4）', value: '864x1152' },
	{ label: '1152x864（4:3）', value: '1152x864' },
	{ label: '768x1344（9:16）', value: '768x1344' },
	{ label: '1344x768（16:9）', value: '1344x768' }
];

export const RESPONSE_FORMAT_OPTIONS = [
	{ label: 'url', value: 'url' },
	{ label: 'b64_json', value: 'b64_json' }
];

export const SEQUENTIAL_OPTIONS = [
	{ label: 'disabled', value: 'disabled' },
	{ label: 'auto', value: 'auto' }
];

export const QUALITY_OPTIONS = [
	{ label: 'standard', value: 'standard' },
	{ label: 'hd', value: 'hd' }
];

export const STYLE_OPTIONS = [
	{ label: 'vivid', value: 'vivid' },
	{ label: 'natural', value: 'natural' }
];

/**
 * 从 profile.modelDefaultConfig（JSON 字符串）中解析模型声明的尺寸选项 `_sizes`。
 */
export function parseProfileSizeOptions(modelDefaultConfig?: string): ImageSizeOption[] | null {
	if (!modelDefaultConfig) {
		return null;
	}
	try {
		const config = JSON.parse(modelDefaultConfig);
		if (config && Array.isArray(config._sizes)) {
			return config._sizes;
		}
	} catch (e) {
		console.warn('解析模型默认尺寸选项失败:', e);
	}
	return null;
}

/**
 * 从 profile.modelDefaultConfig（JSON 字符串）中解析模型声明限制 `_limits`。
 */
export function parseProfileLimits(modelDefaultConfig?: string): ImageProfileLimits {
	if (modelDefaultConfig) {
		try {
			const config = JSON.parse(modelDefaultConfig);
			if (config && config._limits) {
				return {
					max_n: config._limits.max_n || 8,
					max_prompt_length: config._limits.max_prompt_length
				};
			}
		} catch (e) {
			console.warn('[ai/image] 解析 modelDefaultConfig 失败', e);
		}
	}
	return { max_n: 8 };
}
