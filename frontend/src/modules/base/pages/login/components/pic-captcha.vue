<template>
	<div
		class="pic-captcha"
		:class="{
			'is-loading': loading,
			'is-success': status == 'success',
			'is-error': status == 'error'
		}"
	>
		<div v-if="loading" class="captcha-loading">
			<el-icon class="is-loading" :size="18">
				<loading />
			</el-icon>
		</div>

		<template v-else>
			<div class="captcha-track" ref="trackRef" @pointerdown="onTrackPointerDown">
				<div class="captcha-target" :style="{ left: `${targetX}px`, width: `${handleWidth}px` }"></div>
				<div class="captcha-progress" :style="{ width: `${progressWidth}px` }"></div>
				<div
					class="captcha-handle"
					:style="{ width: `${handleWidth}px`, transform: `translateX(${currentX}px)` }"
					@pointerdown.stop="onHandlePointerDown"
				>
					<el-icon :size="18">
						<check v-if="status == 'success'" />
						<close v-else-if="status == 'error'" />
						<right v-else />
					</el-icon>
				</div>
				<span class="captcha-text">{{ displayText }}</span>
			</div>

			<button class="captcha-refresh" type="button" :aria-label="t('刷新')" @click="refresh">
				<el-icon :size="16">
					<refresh-right />
				</el-icon>
			</button>
		</template>
	</div>
</template>

<script lang="ts" setup>
defineOptions({
	name: 'pic-captcha'
});

import { computed, onBeforeUnmount, onMounted, ref } from 'vue';
import { ElMessageBox } from 'element-plus';
import { Check, Close, Loading, RefreshRight, Right } from '@element-plus/icons-vue';
import { useCool } from '/@/cool';
import { useI18n } from 'vue-i18n';

type SliderCaptchaData = {
	type: 'slider';
	trackWidth: number;
	handleWidth: number;
	targetX: number;
	tolerance: number;
	expireSeconds: number;
	label?: string;
};

type TrackPoint = {
	x: number;
	t: number;
};

const emit = defineEmits(['update:modelValue', 'change']);

const { service } = useCool();
const { t } = useI18n();

const trackRef = ref<HTMLElement>();
const loading = ref(false);
const dragging = ref(false);
const status = ref<'idle' | 'success' | 'error'>('idle');
const captchaId = ref('');
const label = ref('');
const trackWidth = ref(256);
const handleWidth = ref(42);
const targetX = ref(0);
const tolerance = ref(6);
const currentX = ref(0);
const startClientX = ref(0);
const startOffsetX = ref(0);
const startTime = ref(0);
const trackPoints = ref<TrackPoint[]>([]);
let resetTimer: ReturnType<typeof window.setTimeout> | undefined;

const maxX = computed(() => Math.max(0, trackWidth.value - handleWidth.value));
const progressWidth = computed(() => Math.min(trackWidth.value, currentX.value + handleWidth.value / 2));
const displayText = computed(() => {
	if (status.value == 'success') {
		return t('验证通过');
	}

	if (status.value == 'error') {
		return t('验证失败，请重试');
	}

	return label.value || t('拖动滑块完成验证');
});

function clearResetTimer() {
	if (resetTimer) {
		window.clearTimeout(resetTimer);
		resetTimer = undefined;
	}
}

function resetState() {
	clearResetTimer();
	dragging.value = false;
	status.value = 'idle';
	currentX.value = 0;
	startClientX.value = 0;
	startOffsetX.value = 0;
	startTime.value = 0;
	trackPoints.value = [];
	emit('change', {
		captchaId: captchaId.value,
		verifyCode: ''
	});
}

function normalizeChallenge(data: unknown): SliderCaptchaData | null {
	if (!data || typeof data != 'object') {
		return null;
	}

	const value = data as Partial<SliderCaptchaData>;

	if (value.type != 'slider') {
		return null;
	}

	const nextTrackWidth = Number(value.trackWidth);
	const nextHandleWidth = Number(value.handleWidth);
	const nextTargetX = Number(value.targetX);
	const nextTolerance = Number(value.tolerance);

	if (
		!Number.isFinite(nextTrackWidth) ||
		!Number.isFinite(nextHandleWidth) ||
		!Number.isFinite(nextTargetX) ||
		!Number.isFinite(nextTolerance)
	) {
		return null;
	}

	return {
		type: 'slider',
		trackWidth: nextTrackWidth,
		handleWidth: nextHandleWidth,
		targetX: nextTargetX,
		tolerance: nextTolerance,
		expireSeconds: Number(value.expireSeconds || 120),
		label: value.label
	};
}

function buildVerifyCode(duration: number) {
	let maxSeenX = 0;

	return JSON.stringify({
		x: Math.round(currentX.value),
		duration,
		track: trackPoints.value.map(e => {
			const nextX = Math.round(e.x);
			maxSeenX = Math.max(maxSeenX, nextX);

			return {
				x: maxSeenX,
				t: e.t
			};
		})
	});
}

async function refresh() {
	loading.value = true;
	resetState();
	emit('update:modelValue', '');

	await service.base.open
		.captcha({
			height: 45,
			width: 256
		})
		.then(({ captchaId: id, data }) => {
			const challenge = normalizeChallenge(data);

			if (!challenge) {
				throw new Error(t('验证码获取失败'));
			}

			captchaId.value = id;
			trackWidth.value = challenge.trackWidth;
			handleWidth.value = challenge.handleWidth;
			targetX.value = challenge.targetX;
			tolerance.value = challenge.tolerance;
			label.value = challenge.label || '';
			emit('update:modelValue', id);
			emit('change', {
				captchaId: id,
				verifyCode: ''
			});
		})
		.catch(err => {
			ElMessageBox.alert((err as Error).message, {
				title: t('提示'),
				type: 'error'
			});
		})
		.finally(() => {
			loading.value = false;
		});
}

function beginDrag(clientX: number) {
	if (loading.value || status.value == 'success') {
		return;
	}

	clearResetTimer();
	dragging.value = true;
	status.value = 'idle';
	startClientX.value = clientX;
	startOffsetX.value = currentX.value;
	startTime.value = Date.now();
	trackPoints.value = [{ x: currentX.value, t: 0 }];
	window.addEventListener('pointermove', onPointerMove);
	window.addEventListener('pointerup', onPointerUp);
}

function onHandlePointerDown(e: PointerEvent) {
	beginDrag(e.clientX);
}

function onTrackPointerDown(e: PointerEvent) {
	const rect = trackRef.value?.getBoundingClientRect();

	if (!rect) {
		return;
	}

	currentX.value = Math.max(0, Math.min(maxX.value, e.clientX - rect.left - handleWidth.value / 2));
	beginDrag(e.clientX);
}

function onPointerMove(e: PointerEvent) {
	if (!dragging.value) {
		return;
	}

	const nextX = startOffsetX.value + e.clientX - startClientX.value;
	currentX.value = Math.max(0, Math.min(maxX.value, nextX));
	trackPoints.value.push({
		x: currentX.value,
		t: Date.now() - startTime.value
	});
}

function onPointerUp() {
	if (!dragging.value) {
		return;
	}

	dragging.value = false;
	window.removeEventListener('pointermove', onPointerMove);
	window.removeEventListener('pointerup', onPointerUp);

	const duration = Date.now() - startTime.value;
	const isMatched = Math.abs(currentX.value - targetX.value) <= tolerance.value;

	if (isMatched) {
		currentX.value = targetX.value;
		status.value = 'success';
		emit('change', {
			captchaId: captchaId.value,
			verifyCode: buildVerifyCode(duration)
		});
		return;
	}

	status.value = 'error';
	emit('change', {
		captchaId: captchaId.value,
		verifyCode: ''
	});
	resetTimer = window.setTimeout(() => {
		status.value = 'idle';
		currentX.value = 0;
		trackPoints.value = [];
	}, 650);
}

onMounted(() => {
	refresh();
});

onBeforeUnmount(() => {
	clearResetTimer();
	window.removeEventListener('pointermove', onPointerMove);
	window.removeEventListener('pointerup', onPointerUp);
});

defineExpose({
	refresh
});
</script>

<style lang="scss" scoped>
.pic-captcha {
	display: grid;
	grid-template-columns: 1fr 36px;
	align-items: center;
	gap: 8px;
	width: 100%;
	min-height: 45px;
	user-select: none;

	.captcha-loading {
		grid-column: 1 / -1;
		display: flex;
		align-items: center;
		justify-content: center;
		height: 45px;
		border-radius: 8px;
		background-color: #f8f8f8;
		color: var(--el-color-info);
	}

	.captcha-track {
		position: relative;
		overflow: hidden;
		height: 45px;
		border-radius: 8px;
		background-color: #f8f8f8;
		cursor: pointer;
		touch-action: none;
	}

	.captcha-target {
		position: absolute;
		top: 6px;
		bottom: 6px;
		z-index: 1;
		border: 1px solid rgba(var(--el-color-primary-rgb), 0.24);
		border-radius: 6px;
		background:
			linear-gradient(
				135deg,
				rgba(var(--el-color-primary-rgb), 0.04) 0%,
				rgba(var(--el-color-primary-rgb), 0.14) 100%
			);
		box-shadow:
			inset 0 0 0 1px rgba(255, 255, 255, 0.72),
			inset 0 6px 14px rgba(var(--el-color-primary-rgb), 0.08);
		pointer-events: none;

		&::before,
		&::after {
			content: '';
			position: absolute;
			left: 50%;
			transform: translateX(-50%);
			border-radius: 999px;
			background-color: rgba(var(--el-color-primary-rgb), 0.28);
		}

		&::before {
			top: 8px;
			height: 4px;
			width: 4px;
			box-shadow:
				-8px 8px 0 rgba(var(--el-color-primary-rgb), 0.16),
				8px 8px 0 rgba(var(--el-color-primary-rgb), 0.16);
		}

		&::after {
			bottom: 8px;
			height: 4px;
			width: 18px;
			opacity: 0.55;
		}
	}

	.captcha-progress {
		position: absolute;
		left: 0;
		top: 0;
		bottom: 0;
		background-color: rgba(var(--el-color-primary-rgb), 0.12);
	}

	.captcha-handle {
		position: absolute;
		left: 0;
		top: 0;
		z-index: 2;
		display: flex;
		align-items: center;
		justify-content: center;
		height: 45px;
		border-radius: 8px;
		background-color: #fff;
		box-shadow: 0 2px 10px rgba(44, 49, 66, 0.16);
		color: var(--el-color-primary);
		cursor: grab;
		touch-action: none;

		&:active {
			cursor: grabbing;
		}
	}

	.captcha-text {
		position: absolute;
		left: 52px;
		right: 16px;
		top: 0;
		height: 45px;
		display: flex;
		align-items: center;
		justify-content: center;
		color: var(--el-color-info);
		font-size: 13px;
		pointer-events: none;
		white-space: nowrap;
	}

	.captcha-refresh {
		display: flex;
		align-items: center;
		justify-content: center;
		height: 36px;
		width: 36px;
		border: 0;
		border-radius: 8px;
		background-color: #f8f8f8;
		color: var(--el-color-info);
		cursor: pointer;

		&:hover {
			color: var(--el-color-primary);
		}
	}

	&.is-success {
		.captcha-target {
			border-color: rgba(var(--el-color-success-rgb), 0.34);
			background:
				linear-gradient(
					135deg,
					rgba(var(--el-color-success-rgb), 0.06) 0%,
					rgba(var(--el-color-success-rgb), 0.16) 100%
				);
			box-shadow:
				inset 0 0 0 1px rgba(255, 255, 255, 0.72),
				inset 0 6px 14px rgba(var(--el-color-success-rgb), 0.1);
		}

		.captcha-progress {
			background-color: rgba(var(--el-color-success-rgb), 0.16);
		}

		.captcha-handle {
			color: var(--el-color-success);
		}
	}

	&.is-error {
		.captcha-target {
			border-color: rgba(var(--el-color-danger-rgb), 0.34);
			background:
				linear-gradient(
					135deg,
					rgba(var(--el-color-danger-rgb), 0.04) 0%,
					rgba(var(--el-color-danger-rgb), 0.14) 100%
				);
			box-shadow:
				inset 0 0 0 1px rgba(255, 255, 255, 0.72),
				inset 0 6px 14px rgba(var(--el-color-danger-rgb), 0.08);
		}

		.captcha-progress {
			background-color: rgba(var(--el-color-danger-rgb), 0.12);
		}

		.captcha-handle {
			color: var(--el-color-danger);
		}
	}
}
</style>
