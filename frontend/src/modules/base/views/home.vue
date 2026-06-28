<template>
	<div class="view-home">
		<div class="view-home__welcome">
			<cl-svg name="home" class="view-home__icon" />
			<h2 class="view-home__title">{{ $t('工作台') }}</h2>
			<p class="view-home__desc">{{ $t('欢迎使用，此处为首页占位内容') }}</p>
		</div>
	</div>
</template>

<script lang="ts" setup>
defineOptions({
	name: 'home'
});
</script>

<style lang="scss" scoped>
.view-home {
	height: 100%;
	box-sizing: border-box;
	display: flex;
	align-items: center;
	justify-content: center;

	&__welcome {
		text-align: center;
	}

	&__icon {
		font-size: 56px;
		color: var(--el-color-primary);
		margin-bottom: 16px;
	}

	&__title {
		margin: 0 0 8px;
		font-size: 22px;
		font-weight: 600;
		color: var(--el-text-color-primary);
	}

	&__desc {
		margin: 0;
		font-size: 14px;
		color: var(--el-text-color-secondary);
	}
}
</style>
