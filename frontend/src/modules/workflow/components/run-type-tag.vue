<template>
	<el-tag v-if="meta" :type="meta.tagType" size="small" :style="meta.style" disable-transitions>
		{{ t(meta.label) }}
	</el-tag>
</template>

<script lang="ts" setup>
defineOptions({
	name: 'run-type-tag'
});

import { computed } from 'vue';
import { useI18n } from 'vue-i18n';

// 实例运行类型徽标：production 蓝 / trial 黄 / eval 紫（与运行记录页分段、log-drawer 头部统一）
const props = defineProps<{
	type?: string | null;
}>();

const { t } = useI18n();

const meta = computed<{ tagType: 'primary' | 'warning'; style?: Record<string, string>; label: string }>(() => {
	switch (props.type) {
		case 'trial':
			return { tagType: 'warning', label: '试运行' };
		case 'eval':
			return {
				tagType: 'primary',
				style: { background: '#7C4DFF', borderColor: '#7C4DFF', color: '#fff' },
				label: '评估'
			};
		default:
			return { tagType: 'primary', label: '生产' };
	}
});
</script>
