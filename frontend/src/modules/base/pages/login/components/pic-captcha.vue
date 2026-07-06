<template>
	<div class="pic-captcha" :class="{ 'is-loading': loading, 'is-dragging': dragging }">
		<div v-if="loading" class="captcha-loading">
			<el-icon class="is-loading" :size="18">
				<loading />
			</el-icon>
		</div>

		<template v-else>
			<div class="captcha-track" ref="trackRef" @pointerdown="onTrackPointerDown">
				<img v-if="bgUrl" class="captcha-bg" :src="bgUrl" draggable="false" alt="captcha" />
				<img
					v-if="sliderUrl"
					class="captcha-slider"
					:src="sliderUrl"
					:style="{ top: `${sliderY}px`, transform: `translateX(${currentX}px)` }"
					draggable="false"
					@pointerdown.stop="onHandlePointerDown"
				/>
				<div class="captcha-progress" :style="{ width: `${progressWidth}px` }"></div>
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
import { Loading, RefreshRight } from '@element-plus/icons-vue';
import { useCool } from '/@/cool';
import { useI18n } from 'vue-i18n';

type SliderCaptchaData = {
	type: 'slider';
	bg: string;
	slider: string;
	sliderWidth: number;
	sliderY: number;
	trackWidth: number;
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
const captchaId = ref('');
const label = ref('');
const trackWidth = ref(300);
const sliderWidth = ref(44);
const sliderY = ref(0);
const bgUrl = ref('');
const sliderUrl = ref('');
const currentX = ref(0);
const startClientX = ref(0);
const startOffsetX = ref(0);
const startTime = ref(0);
const trackPoints = ref<TrackPoint[]>([]);

const maxX = computed(() => Math.max(0, trackWidth.value - sliderWidth.value));
const progressWidth = computed(() =>
	Math.min(trackWidth.value, currentX.value + sliderWidth.value / 2)
);
const displayText = computed(() => label.value || t('拖动滑块对齐缺口完成验证'));

function resetState() {
	dragging.value = false;
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

	const nextSliderWidth = Number(value.sliderWidth);
	const nextSliderY = Number(value.sliderY);
	const nextTrackWidth = Number(value.trackWidth);

	if (
		!Number.isFinite(nextSliderWidth) ||
		!Number.isFinite(nextSliderY) ||
		!Number.isFinite(nextTrackWidth) ||
		typeof value.bg != 'string' ||
		typeof value.slider != 'string'
	) {
		return null;
	}

	return {
		type: 'slider',
		bg: value.bg,
		slider: value.slider,
		sliderWidth: nextSliderWidth,
		sliderY: nextSliderY,
		trackWidth: nextTrackWidth,
		tolerance: Number(value.tolerance || 6),
		expireSeconds: Number(value.expireSeconds || 120),
		label: value.label
	};
}

function buildVerifyCode(duration: number) {
	return JSON.stringify({
		x: Math.round(currentX.value),
		duration,
		track: trackPoints.value.map(e => ({ x: Math.round(e.x), t: e.t }))
	});
}

async function refresh() {
	loading.value = true;
	resetState();
	emit('update:modelValue', '');

	await service.base.open
		.captcha({
			height: 120,
			width: 300
		})
		.then(({ captchaId: id, data }) => {
			const challenge = normalizeChallenge(data);

			if (!challenge) {
				throw new Error(t('验证码获取失败'));
			}

			captchaId.value = id;
			trackWidth.value = challenge.trackWidth;
			sliderWidth.value = challenge.sliderWidth;
			sliderY.value = challenge.sliderY;
			bgUrl.value = challenge.bg;
			sliderUrl.value = challenge.slider;
			label.value = challenge.label || '';
			currentX.value = 0;
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
	if (loading.value) {
		return;
	}

	dragging.value = true;
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

	currentX.value = Math.max(
		0,
		Math.min(maxX.value, e.clientX - rect.left - sliderWidth.value / 2)
	);
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

	// 图像滑块：前端不知 targetX（答案），不本地判断，直接提交轨迹由后端校验
	const duration = Date.now() - startTime.value;
	emit('change', {
		captchaId: captchaId.value,
		verifyCode: buildVerifyCode(duration)
	});
}

onMounted(() => {
	refresh();
});

onBeforeUnmount(() => {
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
	user-select: none;

	.captcha-loading {
		grid-column: 1 / -1;
		display: flex;
		align-items: center;
		justify-content: center;
		height: 120px;
		border-radius: 8px;
		background-color: #f8f8f8;
		color: var(--el-color-info);
	}

	.captcha-track {
		position: relative;
		overflow: hidden;
		height: 120px;
		border-radius: 8px;
		background-color: #f8f8f8;
		cursor: pointer;
		touch-action: none;
	}

	.captcha-bg {
		position: absolute;
		inset: 0;
		width: 100%;
		height: 100%;
		object-fit: cover;
		pointer-events: none;
	}

	.captcha-slider {
		position: absolute;
		left: 0;
		z-index: 2;
		height: 44px;
		cursor: grab;
		touch-action: none;

		&:active {
			cursor: grabbing;
		}
	}

	.captcha-progress {
		position: absolute;
		left: 0;
		bottom: 0;
		height: 3px;
		background-color: rgba(var(--el-color-primary-rgb), 0.5);
		pointer-events: none;
	}

	.captcha-text {
		position: absolute;
		left: 0;
		right: 0;
		bottom: 6px;
		text-align: center;
		color: var(--el-color-info);
		font-size: 12px;
		pointer-events: none;
		white-space: nowrap;
		text-shadow: 0 1px 2px rgba(255, 255, 255, 0.8);
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
}
</style>
