<template>
	<node-config-section :title="$t('模型')">
		<el-form-item :label="$t('生图大模型配置 (Profile)')" required style="margin-bottom: 0">
			<el-select v-model="config.modelProfileCode" style="width: 100%">
				<el-option
					v-for="profile in profiles"
					:key="profile.code"
					:label="profile.name + ' (' + profile.code + ')'"
					:value="profile.code"
				/>
			</el-select>
			<div v-if="selectedProfile" class="profile-meta">
				<el-tag size="small">{{ selectedProfile.providerName || '-' }}</el-tag>
				<el-tag size="small" type="success">{{
					selectedProfile.modelName || selectedProfile.modelId
				}}</el-tag>
			</div>
		</el-form-item>
	</node-config-section>

	<node-config-section :title="$t('提示词')">
		<el-form-item required style="margin-bottom: 0">
			<cl-editor-markdown
				v-model="config.promptTemplate"
				:height="220"
				simple
				placeholder="支持插值变量，例如：画一张关于 {topic} 的图片"
			/>
		</el-form-item>
	</node-config-section>

	<node-config-section :title="$t('参数设置')">
		<el-form-item :label="$t('参考图片 (图生图)')">
			<el-radio-group v-model="imageInputMode" size="small" style="margin-bottom: 6px">
				<el-radio-button value="none">{{ $t('无') }}</el-radio-button>
				<el-radio-button value="variable">{{ $t('变量引用') }}</el-radio-button>
				<el-radio-button value="template">{{ $t('模板渲染') }}</el-radio-button>
			</el-radio-group>
			<el-input
				v-if="imageInputMode === 'variable'"
				v-model="config.imageVariable"
				placeholder="上游变量名，例如：reference_image"
			/>
			<el-input
				v-if="imageInputMode === 'template'"
				v-model="config.imageTemplate"
				placeholder="模板字符串，例如：{image_url}"
			/>
			<div class="field-hint">
				仅火山方舟、阿里百炼、OpenAI 兼容渠道等支持图生图的模型下生效。
			</div>
		</el-form-item>

		<el-form-item :label="$t('图片尺寸 (size)')" style="margin-bottom: 0">
			<el-select v-model="config.size" style="width: 100%" clearable>
				<el-option
					v-for="opt in availableSizeOptions"
					:key="opt.value"
					:label="opt.label"
					:value="opt.value"
				/>
			</el-select>
			<div class="field-hint">留空则使用模型默认尺寸。</div>
		</el-form-item>
	</node-config-section>

	<node-config-section :title="$t('高级参数')" :default-expanded="false">
		<div class="advanced__head">
			<span>{{ $t('高级参数会合并到 options 中，可覆盖表单参数') }}</span>
		</div>
		<el-input
			v-model="config.optionsJson"
			type="textarea"
			:rows="5"
			placeholder='例如: {"quality": "hd", "n": 2}'
		/>
	</node-config-section>

	<node-config-section :title="$t('输出')">
		<el-form-item :label="$t('图片 URL 写入变量')" required style="margin-bottom: 0">
			<el-input v-model="config.outputVariable" placeholder="默认: image_url" />
		</el-form-item>
	</node-config-section>
</template>

<script setup lang="ts">
import { computed, watch } from 'vue';
import NodeConfigSection from './node-config-section.vue';

const props = defineProps<{
	modelValue: Record<string, any>;
	profiles: any[];
}>();

const config = props.modelValue;

const imageInputMode = computed({
	get: () => {
		if (config.imageVariable) return 'variable';
		if (config.imageTemplate) return 'template';
		return 'none';
	},
	set: (mode: string) => {
		if (mode !== 'variable') config.imageVariable = '';
		if (mode !== 'template') config.imageTemplate = '';
	}
});

const selectedProfile = computed(() =>
	props.profiles.find((p: any) => p.code === config.modelProfileCode)
);

const providerKind = computed(() => {
	const p = selectedProfile.value;
	if (!p) return 'unknown';
	const adapter = normalizeToken(p.providerAdapter || p.adapter);
	const providerCode = normalizeToken(p.providerCode);
	const modelCode = normalizeToken(p.modelCode);

	if (
		adapter === 'bailian' ||
		providerCode === 'bailian' ||
		modelCode.includes('wan2.') ||
		modelCode.includes('wanx')
	)
		return 'bailian';
	if (
		adapter === 'volcengine-ark' ||
		providerCode.includes('volcengine') ||
		modelCode.includes('seedream') ||
		modelCode.includes('doubao')
	)
		return 'volcengine-ark';
	if (adapter === 'openai-compatible' || providerCode.includes('openai')) return 'openai';
	if (
		adapter === 'qianfan' ||
		providerCode.includes('qianfan') ||
		modelCode.includes('ernie') ||
		modelCode.includes('irag')
	)
		return 'qianfan';
	if (adapter === 'gemini' || providerCode.includes('gemini') || modelCode.includes('gemini'))
		return 'gemini';
	return 'unknown';
});

function normalizeToken(value: any) {
	return String(value || '')
		.trim()
		.toLowerCase();
}

const sizeOptions = [
	{ label: '1024x1024', value: '1024x1024' },
	{ label: '2048x2048', value: '2048x2048' },
	{ label: '2304x1728', value: '2304x1728' },
	{ label: '1728x2304', value: '1728x2304' },
	{ label: '2560x1440', value: '2560x1440' },
	{ label: '1440x2560', value: '1440x2560' }
];
const bailianSizeOptions = [
	{ label: '1024x1024 (1:1)', value: '1024x1024' },
	{ label: '768x1024 (3:4)', value: '768x1024' },
	{ label: '1024x768 (4:3)', value: '1024x768' },
	{ label: '720x1280 (9:16)', value: '720x1280' },
	{ label: '1280x720 (16:9)', value: '1280x720' }
];
const volcengineSeedream4SizeOptions = [
	{ label: '2560x1440 (16:9)', value: '2560x1440' },
	{ label: '1440x2560 (9:16)', value: '1440x2560' },
	{ label: '2048x2048 (1:1)', value: '2048x2048' }
];
const volcengineSizeOptions = [
	{ label: '1024x1024 (1:1)', value: '1024x1024' },
	{ label: '1024x1536 (2:3)', value: '1024x1536' },
	{ label: '1536x1024 (3:2)', value: '1536x1024' },
	{ label: '768x1344 (9:16)', value: '768x1344' },
	{ label: '1344x768 (16:9)', value: '1344x768' }
];

const availableSizeOptions = computed(() => {
	const profile = selectedProfile.value;
	if (profile && profile.modelDefaultConfig) {
		try {
			const mc = JSON.parse(profile.modelDefaultConfig);
			if (mc && Array.isArray(mc._sizes)) return mc._sizes;
		} catch (e) {}
	}
	if (providerKind.value === 'openai') {
		return [{ label: '自动比例', value: 'auto' }, ...sizeOptions];
	}
	if (providerKind.value === 'bailian') return bailianSizeOptions;
	if (providerKind.value === 'volcengine-ark') {
		const code = normalizeToken(profile?.modelCode || profile?.modelName || '');
		if (code.includes('seedream-4-5') || code.includes('seedream-4-0'))
			return volcengineSeedream4SizeOptions;
		return volcengineSizeOptions;
	}
	return sizeOptions;
});

// 切换 Profile 时自动加载模型默认参数
watch(selectedProfile, profile => {
	if (!profile?.modelDefaultConfig) return;
	try {
		const mc = JSON.parse(profile.modelDefaultConfig);
		if (mc) {
			if (mc.size && availableSizeOptions.value.some(o => o.value === mc.size)) {
				config.size = mc.size;
			}
			if (mc.response_format) {
				// 存入 optionsJson
				try {
					const opts = JSON.parse(config.optionsJson || '{}');
					if (!opts.response_format) opts.response_format = mc.response_format;
					config.optionsJson = JSON.stringify(opts);
				} catch (e) {}
			}
		}
	} catch (e) {
		console.warn('自动加载模型默认参数失败:', e);
	}
});
</script>

<style lang="scss" scoped>
.profile-meta {
	display: flex;
	flex-wrap: wrap;
	gap: 4px;
	margin-top: 6px;
}

.field-hint {
	font-size: 11px;
	color: var(--el-text-color-placeholder);
	margin-top: 4px;
	line-height: 1.4;
}

.advanced__head {
	display: flex;
	align-items: center;
	justify-content: space-between;
	margin-bottom: 6px;
	color: var(--el-text-color-secondary);
	font-size: 12px;
}
</style>
