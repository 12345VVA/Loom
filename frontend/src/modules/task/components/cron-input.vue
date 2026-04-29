<template>
	<div class="cron-input">
		<el-input
			v-model="cronValue"
			:placeholder="placeholder"
			@input="onInput"
			:class="{ 'is-error': error }"
		>
			<template #append>
				<el-button @click="calculateNext">校验</el-button>
			</template>
		</el-input>

		<div v-if="error" class="error-msg">{{ error }}</div>

		<div v-if="nextTimes.length > 0" class="next-times">
			<p class="title">未来执行时间点预览：</p>
			<ul>
				<li v-for="(time, index) in nextTimes" :key="index">
					<el-icon><timer /></el-icon>
					<span>{{ time }}</span>
				</li>
			</ul>
		</div>
	</div>
</template>

<script lang="ts" setup>
import { ref, watch, onMounted } from 'vue';
import { CronExpressionParser } from 'cron-parser';
import dayjs from 'dayjs';
import { Timer } from '@element-plus/icons-vue';

const props = defineProps({
	modelValue: {
		type: String,
		default: ''
	},
	placeholder: {
		type: String,
		default: '* * * * * *'
	}
});

const emit = defineEmits(['update:modelValue']);

const cronValue = ref(props.modelValue);
const nextTimes = ref<string[]>([]);
const error = ref('');

// 校验并计算
function calculateNext() {
	if (!cronValue.value) {
		nextTimes.value = [];
		error.value = '';
		return;
	}

	try {
		const interval = CronExpressionParser.parse(cronValue.value);
		const times: string[] = [];
		for (let i = 0; i < 5; i++) {
			times.push(dayjs(interval.next().toString()).format('YYYY-MM-DD HH:mm:ss'));
		}
		nextTimes.value = times;
		error.value = '';
	} catch (err: any) {
		nextTimes.value = [];
		error.value = '非法的 Cron 表达式';
		console.error(err);
	}
}

function onInput() {
	emit('update:modelValue', cronValue.value);
	calculateNext();
}

watch(
	() => props.modelValue,
	val => {
		cronValue.value = val;
		calculateNext();
	}
);

onMounted(() => {
	if (cronValue.value) {
		calculateNext();
	}
});
</script>

<style lang="scss" scoped>
.cron-input {
	width: 100%;

	.is-error {
		:deep(.el-input__wrapper) {
			box-shadow: 0 0 0 1px var(--el-color-danger) inset;
		}
	}

	.error-msg {
		color: var(--el-color-danger);
		font-size: 12px;
		margin-top: 5px;
	}

	.next-times {
		margin-top: 10px;
		background: var(--el-fill-color-lighter);
		padding: 10px;
		border-radius: 8px;
		border: 1px solid var(--el-border-color-lighter);

		.title {
			font-size: 12px;
			color: var(--el-text-color-secondary);
			margin-bottom: 8px;
			font-weight: bold;
		}

		ul {
			list-style: none;
			padding: 0;
			margin: 0;

			li {
				font-size: 13px;
				color: var(--el-text-color-regular);
				display: flex;
				align-items: center;
				margin-bottom: 4px;
				font-family: var(--el-font-family-mono);

				.el-icon {
					margin-right: 8px;
					color: var(--el-color-primary);
				}

				&:last-child {
					margin-bottom: 0;
				}
			}
		}
	}
}
</style>
