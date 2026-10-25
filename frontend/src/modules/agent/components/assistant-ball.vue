<template>
	<template v-if="!isMobileView && !pageHasWorkspace">
		<div
			v-if="!isOpen"
			ref="ballEl"
			class="assistant-ball"
			:class="{
				'is-hovering': isHovering,
				'is-extended': isExtended,
				'is-dragging': isDragging,
				'has-position': hasPosition
			}"
			:style="ballStyle"
			@pointerdown="onPointerDown"
			@pointermove="onPointerMove"
			@pointerup="onPointerUp"
			@pointercancel="onPointerUp"
			@mouseenter="onMouseEnter"
			@mouseleave="onMouseLeave"
			@mousemove="onMouseMove"
		>
			<img :src="ballIcon" :alt="t('agent.workspace.ballAlt')" draggable="false" />
		</div>

		<div class="assistant-panel" :class="{ 'is-open': isOpen }">
			<chat-workspace v-if="everOpened" ref="workspaceRef" mode="widget" closable @close="isOpen = false" />
		</div>
	</template>

	<Teleport to="body">
		<div v-if="isMobileView && !pageHasWorkspace" class="assistant-mobile" :class="{ 'is-open': isOpen }">
			<chat-workspace v-if="everOpened" mode="widget" closable @close="isOpen = false" />
		</div>
	</Teleport>
</template>

<script lang="ts" setup name="agent-assistant-ball">
/**
 * 全局悬浮 AI 助手（智能体管理目录的常驻入口）。
 *
 * 交互：默认右下完整可见（hover 仅缩放反馈）；可拖拽换位，静止 10s 后收纳进所在
 * 侧缘（hover 伸出）；点击展开右下角工作台侧栏（ChatWorkspace widget 模式）。
 * 移动端全屏接管。侧栏常驻 DOM，首次展开才挂载工作台，避免应用启动即发请求。
 */
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue';
import { useI18n } from 'vue-i18n';
import { useRoute } from 'vue-router';
import ChatWorkspace from './chat-workspace.vue';
import ballIcon from '../static/img/ai-ball.png';

const { t } = useI18n();
const route = useRoute();

// 会话页已内嵌完整 ChatWorkspace（standalone），悬浮球冗余——桌面球与移动面板一并隐藏
const pageHasWorkspace = computed(() => route.path.startsWith('/agent/session'));

const MOBILE_BREAKPOINT = 768;
const DRAG_THRESHOLD_PX = 5;
const COLLAPSE_DELAY_MS = 10_000;
const COLLAPSED_HIDE_PX = 55;
const MOVE_THROTTLE_MS = 1000;

const isMobileView = ref(false);
const isOpen = ref(false);
const everOpened = ref(false);
const isHovering = ref(false);
const isExtended = ref(false);
const hasPosition = ref(false);
const isCollapsed = ref(false);
const dockSide = ref<'left' | 'right'>('right');
const mouseInRange = ref(false);
const isDragging = ref(false);
const isPointerDown = ref(false);
const pointerId = ref<number | null>(null);

const ballEl = ref<HTMLElement | null>(null);
const workspaceRef = ref<{ refresh: () => Promise<void> } | null>(null);
const ballLeft = ref(0);
const ballTop = ref(0);

let dragOffsetX = 0;
let dragOffsetY = 0;
let dragStartClientX = 0;
let dragStartClientY = 0;
let dragStartLeft = 0;
let dragStartTop = 0;
let collapseTimer: ReturnType<typeof setTimeout> | null = null;
let lastMoveTime = 0;

const clamp = (v: number, min: number, max: number) => Math.min(max, Math.max(min, v));

const ballSize = () => {
	const rect = ballEl.value?.getBoundingClientRect();
	return { width: rect?.width ?? 96, height: rect?.height ?? 96 };
};

const clampToViewport = (left: number, top: number) => {
	const { width, height } = ballSize();
	return {
		left: clamp(left, 0, Math.max(0, window.innerWidth - width)),
		top: clamp(top, 0, Math.max(0, window.innerHeight - height))
	};
};

const ballStyle = computed(() => {
	if (!hasPosition.value) return {};
	return { left: `${ballLeft.value}px`, top: `${ballTop.value}px`, right: 'auto', bottom: 'auto' };
});

const clearCollapseTimer = () => {
	if (collapseTimer) {
		clearTimeout(collapseTimer);
		collapseTimer = null;
	}
};

const dockedLeft = (side: 'left' | 'right', collapsed: boolean) => {
	const { width } = ballSize();
	if (!collapsed) return side === 'left' ? 0 : Math.max(0, window.innerWidth - width);
	return side === 'left' ? -COLLAPSED_HIDE_PX : Math.max(0, window.innerWidth - width + COLLAPSED_HIDE_PX);
};

const collapseToSide = () => {
	if (isOpen.value || isMobileView.value || isPointerDown.value || isDragging.value || mouseInRange.value) return;
	if (!hasPosition.value) {
		isExtended.value = false;
		return;
	}
	const { width } = ballSize();
	dockSide.value = ballLeft.value + width / 2 < window.innerWidth / 2 ? 'left' : 'right';
	isCollapsed.value = true;
	isExtended.value = false;
	ballLeft.value = dockedLeft(dockSide.value, true);
};

const expandFromSide = () => {
	if (isOpen.value || isMobileView.value) return;
	clearCollapseTimer();
	isCollapsed.value = false;
	isExtended.value = true;
	if (hasPosition.value) {
		ballLeft.value = dockedLeft(dockSide.value, false);
	}
};

const scheduleCollapse = () => {
	clearCollapseTimer();
	if (isOpen.value || isMobileView.value || isPointerDown.value || isDragging.value || mouseInRange.value) return;
	collapseTimer = setTimeout(collapseToSide, COLLAPSE_DELAY_MS);
};

const handleResize = () => {
	isMobileView.value = window.innerWidth <= MOBILE_BREAKPOINT;
	if (hasPosition.value) {
		const clamped = clampToViewport(ballLeft.value, ballTop.value);
		ballLeft.value = clamped.left;
		ballTop.value = clamped.top;
		if (isCollapsed.value) ballLeft.value = dockedLeft(dockSide.value, true);
	}
};

const toggleChat = () => {
	isOpen.value = !isOpen.value;
	clearCollapseTimer();
};

const onMouseEnter = () => {
	if (isOpen.value || isDragging.value) return;
	mouseInRange.value = true;
	expandFromSide();
	isHovering.value = true;
};

const onMouseMove = () => {
	if (isOpen.value || isDragging.value) return;
	const now = Date.now();
	if (now - lastMoveTime < MOVE_THROTTLE_MS) return;
	lastMoveTime = now;
	mouseInRange.value = true;
	isHovering.value = true;
	if (!isExtended.value) expandFromSide();
};

const onMouseLeave = () => {
	if (isOpen.value || isDragging.value) return;
	mouseInRange.value = false;
	isHovering.value = false;
	scheduleCollapse();
};

const onPointerDown = (e: PointerEvent) => {
	if (isOpen.value) return;
	if (e.pointerType === 'mouse' && e.button !== 0) return;
	if (!ballEl.value) return;

	clearCollapseTimer();
	isPointerDown.value = true;
	isDragging.value = false;
	pointerId.value = e.pointerId;
	isHovering.value = false;
	isExtended.value = true;

	const rect = ballEl.value.getBoundingClientRect();
	dragStartClientX = e.clientX;
	dragStartClientY = e.clientY;
	dragStartLeft = rect.left;
	dragStartTop = rect.top;
	dragOffsetX = e.clientX - rect.left;
	dragOffsetY = e.clientY - rect.top;

	ballEl.value.setPointerCapture(e.pointerId);
	e.preventDefault();
};

const onPointerMove = (e: PointerEvent) => {
	if (!isPointerDown.value || pointerId.value !== e.pointerId || !ballEl.value) return;

	const dx = e.clientX - dragStartClientX;
	const dy = e.clientY - dragStartClientY;
	if (!isDragging.value) {
		if (Math.hypot(dx, dy) < DRAG_THRESHOLD_PX) return;
		isDragging.value = true;
		isCollapsed.value = false;
		hasPosition.value = true;
		ballLeft.value = dragStartLeft;
		ballTop.value = dragStartTop;
	}

	const clamped = clampToViewport(e.clientX - dragOffsetX, e.clientY - dragOffsetY);
	ballLeft.value = clamped.left;
	ballTop.value = clamped.top;
};

const onPointerUp = (e: PointerEvent) => {
	if (!isPointerDown.value || pointerId.value !== e.pointerId) return;

	isPointerDown.value = false;
	pointerId.value = null;
	try {
		ballEl.value?.releasePointerCapture(e.pointerId);
	} catch {
		// 指针已释放时忽略
	}

	const shouldToggle = !isDragging.value;
	isDragging.value = false;
	if (shouldToggle) toggleChat();
	else scheduleCollapse();
};

watch(isOpen, open => {
	if (open) {
		everOpened.value = true;
		clearCollapseTimer();
		// 登录态可能在面板挂载后才建立（401 留下空列表不自愈）——每次展开重拉
		nextTick(() => workspaceRef.value?.refresh());
	} else {
		scheduleCollapse();
	}
});

watch(isMobileView, mobile => {
	if (mobile) clearCollapseTimer();
	else scheduleCollapse();
});

onMounted(() => {
	window.addEventListener('resize', handleResize);
	handleResize();
	scheduleCollapse();
});

onBeforeUnmount(() => {
	window.removeEventListener('resize', handleResize);
	clearCollapseTimer();
});
</script>

<style lang="scss" scoped>
.assistant-ball {
	/* 默认态完整可见且不随 hover 位移——位移量大于露出宽度会让球在悬停时
	「逃走」，指针落空导致点击无反应（真机踩坑）；hover 仅缩放反馈。
	默认位置抬高避开右下角返回顶部按钮。 */
	position: fixed;
	bottom: 120px;
	right: 20px;
	width: 96px;
	height: 96px;
	cursor: pointer;
	z-index: 1000;
	touch-action: none;
	user-select: none;
	transition: all 0.4s cubic-bezier(0.4, 0, 0.2, 1);

	&.is-hovering {
		transform: scale(1.12) rotate(5deg);
	}

	&.has-position {
		right: auto;
		bottom: auto;
	}

	&.has-position:not(.is-dragging) {
		transition:
			left 0.25s cubic-bezier(0.4, 0, 0.2, 1),
			top 0.25s cubic-bezier(0.4, 0, 0.2, 1),
			transform 0.2s cubic-bezier(0.4, 0, 0.2, 1);
	}

	&.is-dragging {
		cursor: grabbing;
		transition: none;
	}

	img {
		width: 100%;
		height: 100%;
		-webkit-user-drag: none;
	}
}

.assistant-panel {
	position: fixed;
	bottom: 16px;
	right: -40px;
	width: min(560px, calc(100vw - 32px));
	height: min(860px, calc(100vh - 32px));
	display: flex;
	flex-direction: column;
	border-radius: 20px;
	border: 1px solid var(--el-border-color-light);
	background-color: var(--el-bg-color);
	box-shadow: var(--el-box-shadow-light);
	z-index: 1001;
	opacity: 0;
	transform: translateY(40px) scale(0.92);
	visibility: hidden;
	overflow: hidden;
	transition: all 0.4s cubic-bezier(0.175, 0.885, 0.32, 1.275);

	&.is-open {
		opacity: 1;
		transform: translateY(0) scale(1);
		visibility: visible;
		right: 16px;
	}
}

.assistant-mobile {
	position: fixed;
	top: 0;
	left: 0;
	width: 100vw;
	height: 100dvh;
	z-index: 99999;
	background-color: var(--el-bg-color);
	display: flex;
	flex-direction: column;
	overflow: hidden;
	transform: translateY(100%);
	transition: transform 0.3s cubic-bezier(0.4, 0, 0.2, 1);

	&.is-open {
		transform: translateY(0);
	}

	:deep(.agent-workspace) {
		width: 100%;
		height: 100%;
		flex: 1;
	}
}
</style>
