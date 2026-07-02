<template>
	<!--
		右键上下文菜单（#23 键盘 a11y：方向键导航 + Enter/Space 触发 + Escape 关闭）。
		菜单项的业务动作由父组件通过 emit 处理，本组件只负责展示与键盘可达性。
	-->
	<div
		v-if="visible"
		ref="rootRef"
		class="context-menu"
		role="menu"
		tabindex="-1"
		:style="{ left: x + 'px', top: y + 'px' }"
		@keydown="onKeydown"
	>
		<div class="context-menu-item" role="menuitem" tabindex="-1" @click="emit('edit')">
			<el-icon><edit /></el-icon>
			<span>{{ t('配置节点') }}</span>
		</div>
		<div
			class="context-menu-item"
			role="menuitem"
			tabindex="-1"
			:aria-disabled="!canTest"
			:class="{ 'is-disabled': !canTest }"
			@click="canTest && emit('test')"
		>
			<el-icon><caret-right /></el-icon>
			<span>{{ t('测试节点') }}</span>
		</div>
		<div class="context-menu-item" role="menuitem" tabindex="-1" @click="emit('duplicate')">
			<el-icon><copy-document /></el-icon>
			<span>{{ t('复制节点') }}</span>
		</div>
		<div
			class="context-menu-item"
			role="menuitem"
			tabindex="-1"
			:aria-disabled="!canDistribute"
			:class="{ 'is-disabled': !canDistribute }"
			@click="canDistribute && emit('distributeH')"
		>
			<el-icon><grid /></el-icon>
			<span>{{ t('水平等距分布') }}</span>
		</div>
		<div
			class="context-menu-item"
			role="menuitem"
			tabindex="-1"
			:aria-disabled="!canDistribute"
			:class="{ 'is-disabled': !canDistribute }"
			@click="canDistribute && emit('distributeV')"
		>
			<el-icon><operation /></el-icon>
			<span>{{ t('垂直等距分布') }}</span>
		</div>
		<div class="context-menu-divider" role="separator" />
		<div
			class="context-menu-item context-menu-item--danger"
			role="menuitem"
			tabindex="-1"
			@click="emit('delete')"
		>
			<el-icon><delete /></el-icon>
			<span>{{ t('删除节点') }}</span>
		</div>
	</div>
</template>

<script lang="ts" setup>
import { ref, watch, nextTick } from 'vue';
import { useI18n } from 'vue-i18n';
import {
	Operation,
	Edit,
	CopyDocument,
	CaretRight,
	Delete,
	Grid
} from '@element-plus/icons-vue';

const props = defineProps<{
	visible: boolean;
	x: number;
	y: number;
	canTest: boolean;
	canDistribute: boolean;
}>();

const emit = defineEmits<{
	(e: 'edit'): void;
	(e: 'test'): void;
	(e: 'duplicate'): void;
	(e: 'distributeH'): void;
	(e: 'distributeV'): void;
	(e: 'delete'): void;
	(e: 'close'): void;
}>();

const { t } = useI18n();
const rootRef = ref<HTMLElement>();

// 键盘 a11y（#23）：方向键在可选项间循环、Enter/Space 触发、Escape 关闭
function onKeydown(event: KeyboardEvent) {
	const root = rootRef.value;
	if (!root) return;
	const items = Array.from(
		root.querySelectorAll<HTMLElement>('.context-menu-item:not(.is-disabled)')
	);
	if (items.length === 0) return;
	const currentIndex = items.findIndex(el => el === document.activeElement);
	if (event.key === 'ArrowDown') {
		event.preventDefault();
		items[(currentIndex + 1) % items.length]?.focus();
	} else if (event.key === 'ArrowUp') {
		event.preventDefault();
		items[(currentIndex - 1 + items.length) % items.length]?.focus();
	} else if (event.key === 'Enter' || event.key === ' ') {
		if (currentIndex >= 0) {
			event.preventDefault();
			items[currentIndex]?.click();
		}
	} else if (event.key === 'Escape') {
		emit('close');
	}
}

// 打开时聚焦首个可选项，使方向键/Enter 可达（#23 a11y）
watch(
	() => props.visible,
	newVal => {
		if (newVal) {
			nextTick(() => {
				rootRef.value
					?.querySelector<HTMLElement>('.context-menu-item:not(.is-disabled)')
					?.focus();
			});
		}
	}
);
</script>

<style lang="scss" scoped>
.context-menu {
	position: fixed;
	z-index: 1000;
	background: #fff;
	border: 1px solid var(--el-border-color-light);
	border-radius: 8px;
	box-shadow: 0 4px 16px rgba(0, 0, 0, 0.12);
	padding: var(--wf-space-xs) 0;
	min-width: 160px;

	.context-menu-item {
		display: flex;
		align-items: center;
		gap: var(--wf-space-sm);
		padding: var(--wf-space-sm) var(--wf-space-lg);
		font-size: 13px;
		cursor: pointer;
		transition: background 0.15s;

		&:hover {
			background: var(--el-fill-color-light);
		}

		.el-icon {
			font-size: 14px;
		}

		&--danger {
			color: var(--el-color-danger);
		}
	}

	.context-menu-divider {
		height: 1px;
		background: var(--el-border-color-lighter);
		margin: var(--wf-space-xs) 0;
	}
}
</style>
