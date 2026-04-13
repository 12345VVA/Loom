<template>
	<error-page :code="502" :desc="$t('马上回来')" />
</template>

<script lang="ts" setup>
defineOptions({
	name: '502'
});

import ErrorPage from './components/error-page.vue';
</script>
