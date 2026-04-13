<template>
	<error-page :code="401" :desc="$t('认证失败，请重新登录！')" />
</template>

<script lang="ts" setup>
defineOptions({
	name: '401'
});

import ErrorPage from './components/error-page.vue';
</script>
