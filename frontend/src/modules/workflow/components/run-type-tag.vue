<template>
	<el-tag v-if="meta" :type="meta.tagType" size="small" :style="meta.style" disable-transitions>
		{{ meta.raw ? meta.label : t(meta.label) }}
	</el-tag>
</template>

<script lang="ts" setup>
defineOptions({
	name: 'run-type-tag'
});

import { computed } from 'vue';
import { useI18n } from 'vue-i18n';

// 实例运行类型徽标：production 蓝 / trial 黄 / eval 紫 / test_node 灰蓝（与运行记录页分段、log-drawer 头部统一）
const props = defineProps<{
	type?: string | null;
}>();

const { t } = useI18n();

const meta = computed<{
	tagType: 'primary' | 'warning' | 'info';
	style?: Record<string, string>;
	label: string;
	/** 未知类型直接展示原值（WFU 低级：后端新增类型时不再误标「生产」） */
	raw?: boolean;
}>(() => {
	switch (props.type) {
		case 'production':
			return { tagType: 'primary', label: '生产' };
		case 'trial':
			return { tagType: 'warning', label: '试运行' };
		case 'eval':
			return {
				tagType: 'primary',
				style: { background: '#7C4DFF', borderColor: '#7C4DFF', color: '#fff' },
				label: '评估'
			};
		case 'test_node':
			return { tagType: 'info', label: '单点' };
		default:
			// null/undefined 沿用生产默认；未知枚举值显示原值，避免误标
			if (!props.type) return { tagType: 'primary', label: '生产' };
			return { tagType: 'info', label: props.type, raw: true };
	}
});
</script>
