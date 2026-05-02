<template>
	<div class="notification-audience-editor">
		<el-checkbox v-model="form.allAdmins">{{ $t('全体管理员') }}</el-checkbox>

		<el-form label-position="top">
			<el-form-item :label="$t('指定用户')">
				<cl-user-select v-model="form.users" multiple />
			</el-form-item>

			<el-form-item :label="$t('指定角色')">
				<el-select v-model="form.roles" multiple filterable clearable class="w-full">
					<el-option
						v-for="item in roleList"
						:key="item.id"
						:label="item.name"
						:value="item.code || item.id || ''"
					/>
				</el-select>
			</el-form-item>

			<el-form-item :label="$t('指定部门')">
				<cl-dept-check v-model="form.departments" />
			</el-form-item>

			<el-form-item :label="$t('部门子级')">
				<el-switch v-model="form.includeChildDepartments" />
			</el-form-item>

			<el-form-item :label="$t('安全条件')">
				<el-select v-model="form.condition" clearable class="w-full">
					<el-option :label="$t('启用管理员')" value="active_admins" />
					<el-option :label="$t('超级管理员')" value="super_admins" />
				</el-select>
			</el-form-item>
		</el-form>
	</div>
</template>

<script lang="ts" setup>
defineOptions({
	name: 'notification-audience-editor'
});

import { onMounted, ref, watch } from 'vue';
import { useCool } from '/@/cool';

type AudienceRule = {
	users: number[];
	roles: Array<number | string>;
	departments: number[];
	tenants: number[];
	includeChildDepartments: boolean;
	allAdmins: boolean;
	condition?: string;
};
type RoleOption = {
	id?: number;
	name?: string;
	code?: string;
};

const props = defineProps<{
	modelValue?: Partial<AudienceRule> | string | null;
}>();

const emit = defineEmits(['update:modelValue']);
const { service } = useCool();
const roleList = ref<RoleOption[]>([]);
const form = ref<AudienceRule>(normalize(props.modelValue));

function normalize(value?: Partial<AudienceRule> | string | null): AudienceRule {
	let data: any = value || {};
	if (typeof value === 'string') {
		try {
			data = JSON.parse(value || '{}');
		} catch {
			data = {};
		}
	}

	return {
		users: data.users || [],
		roles: data.roles || [],
		departments: data.departments || [],
		tenants: data.tenants || [],
		includeChildDepartments: data.includeChildDepartments ?? data.include_child_departments ?? true,
		allAdmins: data.allAdmins ?? data.all_admins ?? false,
		condition: data.condition || undefined
	};
}

watch(
	() => props.modelValue,
	value => {
		form.value = normalize(value);
	},
	{ deep: true }
);

watch(
	form,
	value => {
		emit('update:modelValue', { ...value });
	},
	{ deep: true }
);

onMounted(() => {
	service.base.sys.role.list().then(res => {
		roleList.value = (res || []) as RoleOption[];
	});
});
</script>

<style lang="scss" scoped>
.notification-audience-editor {
	.w-full {
		width: 100%;
	}
}
</style>
