import { ElMessage } from 'element-plus';
import { storage } from '/@/cool/utils';
import { config } from '/@/config';

// CRC-32 计算表
const CRC_TABLE = new Uint32Array(256);
for (let i = 0; i < 256; i++) {
	let c = i;
	for (let k = 0; k < 8; k++) {
		c = c & 1 ? 0xedb88320 ^ (c >>> 1) : c >>> 1;
	}
	CRC_TABLE[i] = c;
}

function crc32(buf: Uint8Array): number {
	let crc = 0xffffffff;
	for (let i = 0; i < buf.length; i++) {
		crc = CRC_TABLE[(crc ^ buf[i]) & 0xff] ^ (crc >>> 8);
	}
	return (crc ^ 0xffffffff) >>> 0;
}

/**
 * 纯前端轻量 ZIP 生成器（采用标准 PKZip 规范，Store 存储格式，无需第三方大体积依赖）
 */
export function createZipBlob(
	files: Array<{ name: string; data: Uint8Array | ArrayBuffer }>
): Blob {
	const textEncoder = new TextEncoder();
	const parts: Uint8Array[] = [];
	const centralDirParts: Uint8Array[] = [];
	let offset = 0;

	for (const file of files) {
		const nameBytes = textEncoder.encode(file.name);
		const dataBytes = file.data instanceof Uint8Array ? file.data : new Uint8Array(file.data);
		const fileCrc = crc32(dataBytes);
		const size = dataBytes.length;

		// 1. Local file header (30 bytes)
		const localHeader = new Uint8Array(30 + nameBytes.length);
		const lView = new DataView(localHeader.buffer);
		lView.setUint32(0, 0x04034b50, true); // signature
		lView.setUint16(4, 20, true); // version needed to extract (2.0)
		lView.setUint16(6, 0x0800, true); // general purpose bit flag (UTF-8)
		lView.setUint16(8, 0, true); // compression method (0 = store)
		lView.setUint16(10, 0, true); // last mod file time
		lView.setUint16(12, 0, true); // last mod file date
		lView.setUint32(14, fileCrc, true); // crc-32
		lView.setUint32(18, size, true); // compressed size
		lView.setUint32(22, size, true); // uncompressed size
		lView.setUint16(26, nameBytes.length, true); // file name length
		lView.setUint16(28, 0, true); // extra field length
		localHeader.set(nameBytes, 30);

		parts.push(localHeader);
		parts.push(dataBytes);

		// 2. Central directory file header (46 bytes)
		const centralHeader = new Uint8Array(46 + nameBytes.length);
		const cView = new DataView(centralHeader.buffer);
		cView.setUint32(0, 0x02014b50, true); // signature
		cView.setUint16(4, 20, true); // version made by
		cView.setUint16(6, 20, true); // version needed to extract
		cView.setUint16(8, 0x0800, true); // general purpose bit flag (UTF-8)
		cView.setUint16(10, 0, true); // compression method (0 = store)
		cView.setUint16(12, 0, true); // last mod time
		cView.setUint16(14, 0, true); // last mod date
		cView.setUint32(16, fileCrc, true); // crc-32
		cView.setUint32(20, size, true); // compressed size
		cView.setUint32(24, size, true); // uncompressed size
		cView.setUint16(28, nameBytes.length, true); // file name length
		cView.setUint16(30, 0, true); // extra field length
		cView.setUint16(32, 0, true); // file comment length
		cView.setUint16(34, 0, true); // disk number start
		cView.setUint16(36, 0, true); // internal file attributes
		cView.setUint32(38, 0, true); // external file attributes
		cView.setUint32(42, offset, true); // relative offset of local header
		centralHeader.set(nameBytes, 46);

		centralDirParts.push(centralHeader);

		offset += localHeader.length + size;
	}

	const centralDirOffset = offset;
	let centralDirSize = 0;
	for (const p of centralDirParts) {
		centralDirSize += p.length;
	}

	// 3. End of central directory record (22 bytes)
	const endRecord = new Uint8Array(22);
	const eView = new DataView(endRecord.buffer);
	eView.setUint32(0, 0x06054b50, true); // signature
	eView.setUint16(4, 0, true); // number of this disk
	eView.setUint16(6, 0, true); // disk where central directory starts
	eView.setUint16(8, files.length, true); // total entries on this disk
	eView.setUint16(10, files.length, true); // total entries
	eView.setUint32(12, centralDirSize, true); // size of central directory
	eView.setUint32(16, centralDirOffset, true); // offset of start of central directory
	eView.setUint16(20, 0, true); // comment length

	const allChunks = [...parts, ...centralDirParts, endRecord];
	return new Blob(allChunks, { type: 'application/zip' });
}

/**
 * 触发浏览器文件下载（支持兼容性降级）
 */
export function triggerDownload(blob: Blob, filename: string) {
	const url = URL.createObjectURL(blob);
	const link = document.createElement('a');
	link.href = url;
	link.download = filename;
	link.style.display = 'none';
	document.body.appendChild(link);
	link.click();
	setTimeout(() => {
		document.body.removeChild(link);
		URL.revokeObjectURL(url);
	}, 1000);
}

/**
 * 判断是否为第三方跨域 URL
 */
function isCrossOriginUrl(url: string): boolean {
	if (!url) return false;
	if (url.startsWith('data:') || url.startsWith('blob:')) return false;
	if (!url.startsWith('http://') && !url.startsWith('https://')) return false;
	try {
		const parsed = new URL(url, window.location.href);
		return parsed.origin !== window.location.origin;
	} catch {
		return false;
	}
}

const RESTRICTED_STORAGE_HOST_SUFFIXES = [
	'volces.com',
	'aliyuncs.com',
	'myqcloud.com',
	'amazonaws.com',
	'blob.core.windows.net'
];

/**
 * 判断是否为常见的受限云存储/AI产物存储外链（通常严格限制 CORS 或没有配置 Access-Control-Allow-Origin）
 *
 * 域级匹配（host 等于后缀或以 .后缀 结尾、tos-/oss- 子域前缀），避免子串误伤
 * 无关域名（如 macos.dev 含 "cos."）。与后端 artifact_service._is_restricted_storage_host 保持一致。
 */
function isLikelyRestrictedStorageUrl(url: string): boolean {
	if (!url || !/^https?:\/\//i.test(url)) return false;
	try {
		const host = new URL(url).hostname.toLowerCase();
		if (host.startsWith('tos-') || host.startsWith('oss-')) return true;
		return RESTRICTED_STORAGE_HOST_SUFFIXES.some((s) => host === s || host.endsWith(`.${s}`));
	} catch {
		return false;
	}
}

/**
 * 通过后端媒体安全代理获取图片二进制（彻底绕过浏览器跨域与 CORS 限制）
 *
 * 认证仅经 Authorization header 传输：access token 不得拼进 URL query，
 * 避免泄露到反代日志/Referer（短 TTL 下载令牌仅用于 /uploads 资源场景）。
 */
async function fetchImageViaBackendProxy(url: string): Promise<ArrayBuffer> {
	const rawToken = storage.session.get('token') || storage.get('token') || '';
	const token = rawToken ? (rawToken.startsWith('Bearer ') ? rawToken : `Bearer ${rawToken}`) : '';

	const proxyUrl = `${config.baseUrl}/admin/media/asset/proxyImage?url=${encodeURIComponent(url)}`;

	const headers: Record<string, string> = {};
	if (token) {
		headers['Authorization'] = token;
	}

	const res = await fetch(proxyUrl, { headers });
	if (!res.ok) {
		throw new Error(`Backend proxy failed with status ${res.status}`);
	}
	return await res.arrayBuffer();
}

/**
 * 强健的多级容错获取图片二进制数据：
 * 0. Data / Blob 协议直通
 * 1. 第三方受限云存储（如火山引擎 TOS、阿里云 OSS 等）直接走后端媒体安全代理，杜绝控制台产生爆红 CORS 报错
 * 2. 常规 Fetch 请求（同源凭据与模式自动适配）
 * 3. 跨域资源代理兜底
 * 4. XMLHttpRequest 降级（原生 arraybuffer）
 * 5. 离屏 Image + Canvas 终极兜底
 */
export async function fetchImageAsArrayBuffer(url: string): Promise<ArrayBuffer> {
	if (!url) throw new Error('Empty URL');

	// 0. 如果是 data: 或 blob: 协议图片，直接由浏览器解码，无需跨域网络请求
	if (url.startsWith('data:') || url.startsWith('blob:')) {
		const res = await fetch(url);
		return await res.arrayBuffer();
	}

	const isCross = isCrossOriginUrl(url);
	const isRestrictedStorage = isLikelyRestrictedStorageUrl(url);

	// 1. 若为已知第三方受限对象存储（如火山引擎 TOS），直接走后端安全代理，杜绝在浏览器控制台产生爆红的 CORS 报错
	if (isCross && isRestrictedStorage) {
		try {
			return await fetchImageViaBackendProxy(url);
		} catch (proxyErr) {
			console.warn(`Backend proxy failed for restricted storage ${url}, trying fallback:`, proxyErr);
		}
	}

	// 2. 尝试常规 fetch
	try {
		const headers: Record<string, string> = {};
		const rawToken = storage.session.get('token') || storage.get('token') || '';
		if (rawToken && !isCross) {
			headers['Authorization'] = rawToken.startsWith('Bearer ') ? rawToken : `Bearer ${rawToken}`;
		}
		const res = await fetch(url, {
			...(isCross ? { mode: 'cors' } : { credentials: 'same-origin' }),
			headers
		});
		if (res.ok) {
			return await res.arrayBuffer();
		}
		console.warn(`Fetch returned status ${res.status} for ${url}, trying fallback`);
	} catch (err) {
		console.warn(`Fetch error for ${url}, trying fallback:`, err);
	}

	// 3. 跨域资源优先通过后端媒体安全代理中转（穿透第三方 TOS/OSS 跨域限制）
	if (isCross) {
		try {
			return await fetchImageViaBackendProxy(url);
		} catch (proxyErr) {
			console.warn(`Backend proxy fallback error for ${url}:`, proxyErr);
		}
	}

	// 4. 尝试 XMLHttpRequest
	try {
		const buffer = await new Promise<ArrayBuffer>((resolve, reject) => {
			const xhr = new XMLHttpRequest();
			xhr.open('GET', url, true);
			xhr.responseType = 'arraybuffer';
			xhr.onload = () => {
				if (xhr.status >= 200 && xhr.status < 300 && xhr.response) {
					resolve(xhr.response);
				} else {
					reject(new Error(`XHR failed with status ${xhr.status}`));
				}
			};
			xhr.onerror = () => reject(new Error('XHR network error'));
			xhr.ontimeout = () => reject(new Error('XHR timeout'));
			xhr.timeout = 15000;
			xhr.send();
		});
		return buffer;
	} catch (err) {
		console.warn(`XHR error for ${url}, trying Canvas fallback:`, err);
	}

	// 5. 终极兜底：利用离屏 Image 加载并通过 Canvas 导出
	return new Promise<ArrayBuffer>((resolve, reject) => {
		const img = new Image();
		img.crossOrigin = 'anonymous';

		img.onload = () => {
			try {
				const canvas = document.createElement('canvas');
				canvas.width = img.naturalWidth || img.width;
				canvas.height = img.naturalHeight || img.height;
				const ctx = canvas.getContext('2d');
				if (!ctx) {
					reject(new Error('Failed to get canvas 2d context'));
					return;
				}
				ctx.drawImage(img, 0, 0);

				const cleanUrl = url.split('?')[0].toLowerCase();
				let mime = 'image/jpeg';
				if (cleanUrl.endsWith('.png')) mime = 'image/png';
				else if (cleanUrl.endsWith('.webp')) mime = 'image/webp';

				canvas.toBlob(blob => {
					if (!blob) {
						reject(new Error('Canvas toBlob failed'));
						return;
					}
					const reader = new FileReader();
					reader.onloadend = () => {
						if (reader.result instanceof ArrayBuffer) {
							resolve(reader.result);
						} else {
							reject(new Error('FileReader failed to read ArrayBuffer'));
						}
					};
					reader.onerror = () => reject(new Error('FileReader error'));
					reader.readAsArrayBuffer(blob);
				}, mime);
			} catch (e) {
				reject(e);
			}
		};

		img.onerror = () => reject(new Error(`Image element failed to load ${url}`));
		img.src = url;
	});
}

/**
 * 单张图片下载：通过三级容错转 Blob，避免浏览器直接在新标签页打开
 */
export async function downloadSingleImage(url: string, filename?: string) {
	try {
		const data = await fetchImageAsArrayBuffer(url);
		const cleanUrl = url.split('?')[0].toLowerCase();
		let mime = 'image/jpeg';
		if (cleanUrl.endsWith('.png')) mime = 'image/png';
		else if (cleanUrl.endsWith('.webp')) mime = 'image/webp';

		const blob = new Blob([data], { type: mime });
		let finalName = filename;
		if (!finalName) {
			const nameFromUrl = cleanUrl.substring(cleanUrl.lastIndexOf('/') + 1);
			finalName = nameFromUrl || `image_${Date.now()}.jpeg`;
		}

		triggerDownload(blob, finalName);
		ElMessage.success('开始下载图片');
	} catch (err: any) {
		console.error('Download image error, fallback to direct anchor:', err);
		// 降级：直接用 a 标签打开/下载
		const link = document.createElement('a');
		link.href = url;
		link.download = filename || `image_${Date.now()}.png`;
		link.target = '_blank';
		document.body.appendChild(link);
		link.click();
		document.body.removeChild(link);
	}
}

export interface ImageDownloadItem {
	url: string;
	title?: string;
	subtitle?: string;
}

/**
 * 批量将多张图片打包为 ZIP 文件并一键下载
 */
export async function downloadImagesAsZip(
	items: ImageDownloadItem[],
	zipFilename = 'workflow_images.zip',
	onProgress?: (current: number, total: number) => void
) {
	if (!items || items.length === 0) {
		ElMessage.warning('没有可下载的图片');
		return;
	}

	const files: Array<{ name: string; data: ArrayBuffer }> = [];
	const total = items.length;

	for (let i = 0; i < total; i++) {
		const item = items[i];
		if (onProgress) onProgress(i + 1, total);

		try {
			const data = await fetchImageAsArrayBuffer(item.url);

			// 智能构造语义化文件名
			const cleanUrl = item.url.split('?')[0];
			const extMatch = cleanUrl.match(/\.(png|jpe?g|webp|gif|svg)$/i);
			const ext = extMatch ? extMatch[0].toLowerCase() : '.jpeg';

			let baseName = '';
			if (item.subtitle) {
				// 清洗文件名中的非法字符
				const safeSubtitle = item.subtitle.replace(/[\\/:*?"<>|\r\n]/g, '').trim();
				baseName = safeSubtitle.substring(0, 30);
			} else if (item.title) {
				baseName = item.title.replace(/[\\/:*?"<>|\r\n]/g, '').trim();
			}

			const seq = String(i + 1).padStart(2, '0');
			const fileName = baseName ? `${seq}_${baseName}${ext}` : `${seq}_image${ext}`;

			files.push({
				name: fileName,
				data
			});
		} catch (e) {
			console.error(`Failed to load image for ZIP packaging: ${item.url}`, e);
		}
	}

	if (files.length === 0) {
		ElMessage.error('图片获取失败，无法打包');
		return;
	}

	const zipBlob = createZipBlob(files);
	triggerDownload(zipBlob, zipFilename);
	if (files.length < total) {
		ElMessage.warning(`已打包 ${files.length}/${total} 张图片（部分图片获取失败）`);
	} else {
		ElMessage.success(`成功打包下载 ${files.length} 张图片！`);
	}
}
