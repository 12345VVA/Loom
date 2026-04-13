<template>
	<error-page :code="404" :desc="$t('找不到您要查找的页面')" />
</template>

<script lang="ts" setup>
defineOptions({
	name: '404'
});

import ErrorPage from './components/error-page.vue';
</script>
