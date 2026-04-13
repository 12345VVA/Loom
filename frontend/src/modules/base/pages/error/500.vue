<template>
	<error-page :code="500" :desc="$t('糟糕，出了点问题')" />
</template>

<script lang="ts" setup>
defineOptions({
	name: '500'
});

import ErrorPage from './components/error-page.vue';
</script>
