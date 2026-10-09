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
			<el-select
				v-model="config.size"
				style="width: 100%"
				clearable
				filterable
				:allow-create="allowCustomSize"
				default-first-option
				:placeholder="sizePlaceholder"
			>
				<el-option
					v-for="opt in availableSizeOptions"
					:key="opt.value"
					:label="opt.label"
					:value="opt.value"
				/>
			</el-select>
			<div class="field-hint">{{ sizeHint }}</div>
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
import {
	detectProviderKind,
	parseProfileSizeOptions,
	parseProfileAllowCustomSize,
	parseProfileSizeFormat,
	BASE_SIZE_OPTIONS,
	BAILIAN_SIZE_OPTIONS,
	PORYF_SIZE_OPTIONS,
	VOLCENGINE_SIZE_OPTIONS,
	VOLCENGINE_SEEDREAM4_SIZE_OPTIONS,
	TOAPIS_RATIO_SIZE_OPTIONS
} from '/$/ai/utils/image-providers';

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

const providerKind = computed(() => detectProviderKind(selectedProfile.value));

const allowCustomSize = computed(() =>
	parseProfileAllowCustomSize(selectedProfile.value?.modelDefaultConfig, true)
);

const sizeFormat = computed(() =>
	parseProfileSizeFormat(selectedProfile.value?.modelDefaultConfig)
);

const sizePlaceholder = computed(() => {
	if (allowCustomSize.value) {
		return sizeFormat.value === 'ratio'
			? '请选择或输入比例（如 3:4, 16:9）'
			: '请选择或输入尺寸（如 864x1152, 1024x1024）';
	}
	return '请选择模型预设尺寸';
});

const sizeHint = computed(() => {
	if (sizeFormat.value === 'ratio') {
		return allowCustomSize.value
			? '当前模型为比例模式，可直接选择或自定义输入比例（例如 3:4、16:9）。'
			: '当前模型仅支持官方指定比例，请从下拉列表中选择。';
	}
	if (!allowCustomSize.value) {
		return '当前模型仅支持指定预设尺寸，不支持自定义输入。留空使用默认。';
	}
	return '留空则使用模型默认尺寸；支持下拉选择或直接键入自定义分辨率（如 864x1152）。';
});

const availableSizeOptions = computed(() => {
	const profile = selectedProfile.value;
	const customSizes = parseProfileSizeOptions(profile?.modelDefaultConfig);
	if (customSizes && customSizes.length > 0) {
		return customSizes;
	}
	if (providerKind.value === 'toapis') {
		return TOAPIS_RATIO_SIZE_OPTIONS;
	}
	if (providerKind.value === 'poryf') {
		return PORYF_SIZE_OPTIONS;
	}
	if (providerKind.value === 'openai') {
		return [{ label: '自动比例', value: 'auto' }, ...BASE_SIZE_OPTIONS];
	}
	if (providerKind.value === 'bailian') {
		return BAILIAN_SIZE_OPTIONS;
	}
	if (providerKind.value === 'volcengine-ark') {
		const code = String(profile?.modelCode || profile?.modelName || '').toLowerCase();
		if (code.includes('seedream-4-5') || code.includes('seedream-4-0')) {
			return VOLCENGINE_SEEDREAM4_SIZE_OPTIONS;
		}
		return VOLCENGINE_SIZE_OPTIONS;
	}
	return BASE_SIZE_OPTIONS;
});

// 切换 Profile 时自动加载模型默认参数
watch(selectedProfile, profile => {
	if (!profile?.modelDefaultConfig) return;
	try {
		const mc = JSON.parse(profile.modelDefaultConfig);
		if (mc) {
			if (mc.size && (!config.size || availableSizeOptions.value.some(o => o.value === mc.size))) {
				config.size = mc.size;
			}
			if (mc.response_format) {
				// 存入 optionsJson
				try {
					const opts = JSON.parse(config.optionsJson || '{}');
					if (!opts.response_format) opts.response_format = mc.response_format;
					config.optionsJson = JSON.stringify(opts);
				} catch (e) {
					console.warn('[workflow/image-generator-config] 写入 response_format 到 optionsJson 失败', e);
				}
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
