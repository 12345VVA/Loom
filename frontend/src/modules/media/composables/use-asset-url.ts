import { getCurrentInstance, onMounted, ref } from 'vue';
import { useCool } from '/@/cool';
import { config } from '/@/config';

// 全局单例共享下载令牌与有效期，杜绝各组件独立持有导致状态过期不一致
const globalDownloadToken = ref('');
const globalDownloadTokenExpireAt = ref(0);
let globalTokenPromise: Promise<string> | null = null;
let globalRefreshTimer: ReturnType<typeof setTimeout> | null = null;

/**
 * 媒体资产访问地址 + 专用下载令牌（media 与 workflow 产物视图共用）。
 *
 * 令牌与 access token 隔离，避免其通过 ?token= 泄露到日志/Referer/分享串；
 * 采用全局单例管理，过期前自动续签，切后台唤醒或窗口获得焦点时自动按需刷新。
 */
export function useAssetUrl() {
	const { service } = useCool();

	async function ensureDownloadToken(force = false): Promise<string> {
		// 剩余有效期 > 60s 且非强制刷新直接复用
		if (
			!force &&
			globalDownloadToken.value &&
			Date.now() < globalDownloadTokenExpireAt.value - 60000
		) {
			return globalDownloadToken.value;
		}

		if (globalTokenPromise) {
			return globalTokenPromise;
		}

		globalTokenPromise = (async () => {
			try {
				const mediaService = (service as any)?.media?.asset;
				if (!mediaService?.downloadToken) return globalDownloadToken.value;

				const res = await mediaService.downloadToken();
				globalDownloadToken.value = res?.token || '';
				globalDownloadTokenExpireAt.value = Date.now() + (res?.expire || 7200) * 1000;

				// 提前 2 分钟续签，最少 10 秒
				const delay = Math.max(
					globalDownloadTokenExpireAt.value - Date.now() - 120000,
					10000
				);
				if (globalRefreshTimer) clearTimeout(globalRefreshTimer);
				globalRefreshTimer = setTimeout(() => ensureDownloadToken(true), delay);
			} catch (e) {
				console.warn('Failed to refresh download token:', e);
			} finally {
				globalTokenPromise = null;
			}
			return globalDownloadToken.value;
		})();

		return globalTokenPromise;
	}

	function assetUrl(url?: string): string {
		if (!url) {
			return '';
		}
		const s = url.trim();
		if (s.startsWith('data:') || s.startsWith('blob:')) {
			return s;
		}

		// 统一剥离 URL 中已存在的旧 token，防止旧 token 污染或重复拼接多层参数
		let cleanUrl = s;
		if (cleanUrl.includes('token=')) {
			cleanUrl = cleanUrl
				.replace(/([?&])token=[^&]*/g, '')
				.replace(/[?&]$/, '');
		}

		// 检查是否为指向 Loom 本地上传资源（包含 uploads/）
		const uploadsIdx = cleanUrl.indexOf('uploads/');
		const isUploads = uploadsIdx !== -1;

		if (!isUploads) {
			// 不是 uploads 资源（如纯远程 TOS/OSS 外链或静态文件），直接原样返回
			return cleanUrl;
		}

		// 如果是包含协议的全量外链（http:// 或 https:// 或 //）
		if (/^(https?:)?\/\//i.test(cleanUrl)) {
			// 检查是否指向当前前端域或本地后端开发服务器
			const isLocalHost =
				cleanUrl.includes('127.0.0.1') ||
				cleanUrl.includes('localhost') ||
				(typeof window !== 'undefined' && !!window.location?.host && cleanUrl.includes(window.location.host));

			// 如果不是本地服务的全量外链（例如第三方 CDN 也叫 uploads/），直接原样返回，不注入内部 token
			if (!isLocalHost) {
				return cleanUrl;
			}
		}

		// 核心关键：无论输入是 /uploads/...、uploads/...、/dev/uploads/... 还是 /dev/dev/uploads/...
		// 均截取自 uploads/ 开始的纯净相对路径，彻底杜绝 /dev/dev/ 等多重 baseUrl 嵌套前缀
		const relUploadsPath = cleanUrl.substring(uploadsIdx);

		// 获取纯净的标准 baseUrl 前缀（去除末尾多余斜杠）
		const base = (config.baseUrl || '').replace(/\/+$/, '');
		const finalPath = base ? `${base}/${relUploadsPath}` : `/${relUploadsPath}`;

		const token = globalDownloadToken.value;
		// 如果 token 为空或即将过期（10 秒内），触发异步刷新
		if (!token || Date.now() >= globalDownloadTokenExpireAt.value - 10000) {
			ensureDownloadToken();
			// 如果当前没有 token，返回尚未带 token 的 finalPath，避免空白返回阻断组件挂载，
			// 一旦 token 异步获取完成，依赖 globalDownloadToken 的响应式属性或重试将自动补齐
			if (!token) {
				return finalPath;
			}
		}

		const sep = finalPath.includes('?') ? '&' : '?';
		return `${finalPath}${sep}token=${token}`;
	}

	if (getCurrentInstance()) {
		onMounted(() => {
			ensureDownloadToken();
		});
	}

	return {
		assetUrl,
		ensureDownloadToken,
		downloadToken: globalDownloadToken
	};
}

// 页面可见性改变（从后台切回前台）或窗口获得焦点时自动按需续签
if (typeof window !== 'undefined') {
	const checkAndRefresh = () => {
		if (
			globalDownloadToken.value &&
			Date.now() >= globalDownloadTokenExpireAt.value - 120000
		) {
			globalDownloadTokenExpireAt.value = 0;
			// 触发刷新
			useAssetUrl().ensureDownloadToken(true);
		}
	};
	window.addEventListener('visibilitychange', () => {
		if (document.visibilityState === 'visible') {
			checkAndRefresh();
		}
	});
	window.addEventListener('focus', checkAndRefresh);
}
