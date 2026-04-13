<template>
	<error-page :code="403" :desc="$t('您无权访问此页面')" />
</template>

<script lang="ts" setup>
defineOptions({
	name: '403'
});

import ErrorPage from './components/error-page.vue';
</script>
