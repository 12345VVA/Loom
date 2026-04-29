<template>
	<div class="pic-captcha" @click="refresh">
		<img v-if="captchaSrc" class="captcha-img" :src="captchaSrc" alt="" />

		<template v-else>
			<el-icon class="is-loading" :size="18">
				<loading />
			</el-icon>
		</template>
	</div>
</template>

<script lang="ts" setup>
defineOptions({
	name: 'pic-captcha'
});

import { onBeforeUnmount, onMounted, ref } from 'vue';
import { ElMessageBox } from 'element-plus';
import { Loading } from '@element-plus/icons-vue';
import { useCool } from '/@/cool';
import { useI18n } from 'vue-i18n';

const emit = defineEmits(['update:modelValue', 'change']);

const { service } = useCool();
const { t } = useI18n();

// base64
const base64 = ref('');

// svg
const svg = ref('');

const captchaSrc = ref('');
let objectUrl = '';

function releaseObjectUrl() {
	if (objectUrl) {
		URL.revokeObjectURL(objectUrl);
		objectUrl = '';
	}
}

// 刷新
async function refresh() {
	releaseObjectUrl();
	svg.value = '';
	base64.value = '';
	captchaSrc.value = '';

	await service.base.open
		.captcha({
			height: 45,
			width: 150,
			color: '#2c3142'
		})
		.then(({ captchaId, data }) => {
			if (data) {
				if (data.includes(';base64,')) {
					base64.value = data;
					captchaSrc.value = data;
				} else {
					svg.value = data;
					objectUrl = URL.createObjectURL(new Blob([data], { type: 'image/svg+xml' }));
					captchaSrc.value = objectUrl;
				}

				emit('update:modelValue', captchaId);
				emit('change', {
					base64,
					svg,
					captchaId
				});
			} else {
				ElMessageBox.alert(t('验证码获取失败'), {
					title: t('提示'),
					type: 'error'
				});
			}
		})
		.catch(err => {
			ElMessageBox.alert(err.message, {
				title: t('提示'),
				type: 'error'
			});
		});
}

onMounted(() => {
	refresh();
});

onBeforeUnmount(() => {
	releaseObjectUrl();
});

defineExpose({
	refresh
});
</script>

<style lang="scss" scoped>
.pic-captcha {
	display: flex;
	justify-content: center;
	align-items: center;
	cursor: pointer;
	height: 45px;
	width: 150px;
	position: relative;
	user-select: none;

	.captcha-img {
		height: 100%;
	}

	.is-loading {
		position: absolute;
		right: 15px;
	}
}
</style>
