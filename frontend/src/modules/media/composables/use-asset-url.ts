import { onMounted, onUnmounted, ref } from 'vue';
import { useCool } from '/@/cool';
import { config } from '/@/config';

/**
 * 媒体资产访问地址 + 专用下载令牌（media 与 workflow 产物视图共用）。
 *
 * 令牌短 TTL、与 access token 隔离，避免其通过 ?token= 泄露到日志/Referer/分享串；
 * 过期前 60s 自动续签，组件卸载即停止（防孤儿定时器无限续签）。
 */
export function useAssetUrl() {
	const { service } = useCool();
	const mediaService = (service as any).media.asset;

	const downloadToken = ref('');
	const downloadTokenExpireAt = ref(0);
	let downloadTokenTimer: ReturnType<typeof setTimeout> | null = null;
	// 组件卸载标志：阻止 await 期间卸载后继续写状态/设新 timer
	let unmounted = false;

	async function ensureDownloadToken(): Promise<string> {
		// 剩余有效期 > 30s 直接复用
		if (downloadToken.value && Date.now() < downloadTokenExpireAt.value - 30000) {
			return downloadToken.value;
		}
		try {
			const res = await mediaService.downloadToken();
			if (unmounted) return downloadToken.value;
			downloadToken.value = res?.token || '';
			downloadTokenExpireAt.value = Date.now() + (res?.expire || 300) * 1000;
			const delay = Math.max(downloadTokenExpireAt.value - Date.now() - 60000, 10000);
			if (downloadTokenTimer) clearTimeout(downloadTokenTimer);
			downloadTokenTimer = setTimeout(() => ensureDownloadToken(), delay);
		} catch {
			if (unmounted) return downloadToken.value;
			downloadToken.value = '';
		}
		return downloadToken.value;
	}

	function assetUrl(url?: string) {
		if (!url) {
			return '';
		}
		if (/^(https?:)?\/\//.test(url) || url.startsWith('data:')) {
			return url;
		}
		if (url.startsWith('/uploads/')) {
			const token = downloadToken.value;
			// token 未就绪时返回空串，避免发出无 token 的 401 请求（污染浏览器缓存/破图）；
			// token 到位后 ref 变化触发响应式重渲染，src 重新带上 token 加载。
			if (!token) return '';
			const sep = url.includes('?') ? '&' : '?';
			return `${config.baseUrl}${url}${sep}token=${token}`;
		}
		return url;
	}

	onMounted(() => {
		ensureDownloadToken();
	});

	onUnmounted(() => {
		unmounted = true;
		if (downloadTokenTimer) clearTimeout(downloadTokenTimer);
	});

	return { assetUrl, ensureDownloadToken, downloadToken };
}
