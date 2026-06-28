<template>
	<div class="node-config-section" :class="{ 'is-collapsed': !isExpanded }">
		<div class="section-header" role="button" :aria-expanded="isExpanded" @click="toggle">
			<div class="section-title">
				<el-icon class="arrow-icon" :class="{ 'is-rotated': !isExpanded }"
					><arrow-down
				/></el-icon>
				{{ title }}
				<el-tooltip v-if="tooltip" placement="top" effect="dark" :content="tooltip">
					<el-icon class="hint-icon" @click.stop><info-filled /></el-icon>
				</el-tooltip>
			</div>

			<div class="section-actions" @click.stop>
				<slot name="actions"></slot>
			</div>
		</div>

		<el-collapse-transition>
			<div v-show="isExpanded" class="section-content-wrapper">
				<div class="section-content">
					<slot></slot>
				</div>
			</div>
		</el-collapse-transition>
	</div>
</template>

<script setup lang="ts">
import { ref, watch, inject, computed, type Ref } from 'vue';
import { ArrowDown, InfoFilled } from '@element-plus/icons-vue';
import { SECTION_COLLAPSE_STATE_KEY, CONFIG_PANEL_NODE_ID_KEY } from '../constants';

const props = withDefaults(
	defineProps<{
		title: string;
		tooltip?: string;
		defaultExpanded?: boolean;
		/** v-model 绑定展开状态（可选，不传则使用内部状态） */
		modelValue?: boolean;
	}>(),
	{
		defaultExpanded: true
	}
);

const emit = defineEmits<{
	(e: 'update:modelValue', value: boolean): void;
}>();

// 注入折叠状态持久化 Map 和当前节点 ID
const sectionCollapseState = inject(SECTION_COLLAPSE_STATE_KEY, null);
const nodeId = inject<Ref<string>>(CONFIG_PANEL_NODE_ID_KEY, ref(''));

// 生成唯一存储键：nodeId:title
const storageKey = computed(() => `${nodeId.value}:${props.title}`);

// 内部折叠状态，由 defaultExpanded 初始化
const isExpanded = ref(props.defaultExpanded);

// 初始化时从持久化状态恢复
if (sectionCollapseState?.value?.has(storageKey.value)) {
	isExpanded.value = sectionCollapseState.value.get(storageKey.value)!;
}

// 如果外部传了 v-model，同步到内部状态
watch(
	() => props.modelValue,
	val => {
		if (val !== undefined && val !== isExpanded.value) {
			isExpanded.value = val;
		}
	},
	{ immediate: true }
);

// 当 storageKey 变化（切换节点）时，恢复对应折叠状态
watch(storageKey, newKey => {
	if (sectionCollapseState?.value?.has(newKey)) {
		isExpanded.value = sectionCollapseState.value.get(newKey)!;
	} else {
		isExpanded.value = props.defaultExpanded;
	}
});

function toggle() {
	isExpanded.value = !isExpanded.value;
	// 持久化折叠状态
	if (sectionCollapseState?.value) {
		sectionCollapseState.value.set(storageKey.value, isExpanded.value);
	}
	emit('update:modelValue', isExpanded.value);
}
</script>

<style lang="scss" scoped>
.node-config-section {
	border-bottom: 1px solid var(--el-border-color-lighter);
	background-color: #fff;

	&:first-child {
		border-top: 1px solid var(--el-border-color-lighter);
	}

	.section-header {
		display: flex;
		justify-content: space-between;
		align-items: center;
		padding: 12px 16px;
		cursor: pointer;
		user-select: none;
		transition: background-color 0.2s;

		&:hover {
			background-color: var(--el-fill-color-light);
		}

		.section-title {
			display: flex;
			align-items: center;
			font-size: 13px;
			font-weight: 600;
			color: var(--el-text-color-primary);

			.arrow-icon {
				margin-right: 6px;
				font-size: 12px;
				color: var(--el-text-color-secondary);
				transition: transform 0.3s;

				&.is-rotated {
					transform: rotate(-90deg);
				}
			}

			.hint-icon {
				margin-left: 6px;
				font-size: 14px;
				color: var(--el-text-color-placeholder);
				cursor: help;
			}
		}

		.section-actions {
			display: flex;
			align-items: center;
			gap: 4px;

			/* JSON 输出控制栏兼容样式 */
			:deep(.json-actions-divider) {
				width: 1px;
				height: 14px;
				background-color: var(--el-border-color);
				margin: 0 8px;
			}

			:deep(.action-icon-btn) {
				display: inline-flex;
				align-items: center;
				justify-content: center;
				width: 24px;
				height: 24px;
				border-radius: 4px;
				color: var(--el-text-color-secondary);
				cursor: pointer;
				transition:
					background-color 0.2s,
					color 0.2s;
				margin-left: 2px;

				&:hover {
					background-color: var(--el-fill-color);
					color: var(--el-color-primary);
				}

				&.primary {
					color: var(--el-color-primary);
					background-color: var(--el-color-primary-light-9);
					&:hover {
						background-color: var(--el-color-primary-light-8);
					}
				}

				.el-icon {
					font-size: 14px;
				}
			}

			:deep(.output-format-btn) {
				display: inline-flex;
				align-items: center;
				padding: 2px 8px;
				font-size: 12px;
				color: var(--el-color-primary);
				background-color: var(--el-color-primary-light-9);
				border-radius: 4px;
				cursor: pointer;
				transition: background-color 0.2s;
				user-select: none;

				&:hover {
					background-color: var(--el-color-primary-light-8);
				}

				.el-icon {
					font-size: 12px;
				}
			}
		}
	}

	.section-content-wrapper {
		.section-content {
			padding: 0 16px 16px 16px;
		}
	}
}
</style>
