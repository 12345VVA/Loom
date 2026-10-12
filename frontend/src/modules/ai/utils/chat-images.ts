/**
 * 对话测试页多模态图片工具（纯函数层，便于单测）。
 *
 * 图片以 data URI 直发（OpenAI 风格 IR image_url part）：本地 /uploads 回环 URL
 * 会被后端 SSRF 防御拒绝，data URI 在三渠道 adapter 均为直通路径；对话测试页
 * 消息仅前端内存态，不违反工作流「URL-as-medium」红线（该红线针对 checkpoint）。
 */

/** 允许的图片 MIME（对齐后端 media_fetch IMAGE_MIME_WHITELIST，排除可内嵌脚本的 SVG） */
export const CHAT_IMAGE_MIME_WHITELIST = ['image/png', 'image/jpeg', 'image/webp', 'image/gif'];

/** 单张大小上限（后端 media_fetch 拉取上限 10MB，前端收紧到 5MB 控制 base64 请求体膨胀） */
export const CHAT_IMAGE_MAX_SIZE_MB = 5;

/** 每条消息图片张数上限 */
export const CHAT_IMAGE_MAX_COUNT = 4;

/** 校验单张图片文件，合法返回 null，否则返回错误文案（本身即 i18n key）。 */
export function validateImageFile(file: File): string | null {
	if (!CHAT_IMAGE_MIME_WHITELIST.includes(file.type)) {
		return '不支持的图片类型（仅支持 PNG / JPEG / WebP / GIF）';
	}
	if (file.size > CHAT_IMAGE_MAX_SIZE_MB * 1024 * 1024) {
		return `单张图片不能超过 ${CHAT_IMAGE_MAX_SIZE_MB}MB`;
	}
	return null;
}

/** 读取文件为 data URI。 */
export function readFileAsDataUri(file: File): Promise<string> {
	return new Promise((resolve, reject) => {
		const reader = new FileReader();
		reader.onload = () => resolve(String(reader.result || ''));
		reader.onerror = () => reject(reader.error);
		reader.readAsDataURL(file);
	});
}

/** OpenAI 风格消息 content part（对话测试页多模态 IR，三渠道 adapter 直通） */
export interface ChatTextContentPart {
	type: 'text';
	text: string;
}

export interface ChatImageUrlContentPart {
	type: 'image_url';
	image_url: { url: string };
}

export type ChatContentPart = ChatTextContentPart | ChatImageUrlContentPart;

export type ChatMessageContent = string | ChatContentPart[];

/**
 * 组装消息 content（OpenAI 风格 IR）：
 * - 无图 → 原样返回 str（与既有纯文本请求格式完全一致，后端零感知）；
 * - 有图 → [{type:'text'},{type:'image_url',image_url:{url:dataUri}},...]，文本为空时省略 text part。
 */
export function buildMessageContent(text: string, images?: string[]): ChatMessageContent {
	if (!images || !images.length) {
		return text;
	}
	const parts: ChatContentPart[] = images.map(
		(url): ChatImageUrlContentPart => ({ type: 'image_url', image_url: { url } })
	);
	const trimmed = (text || '').trim();
	if (trimmed) {
		parts.unshift({ type: 'text', text: trimmed });
	}
	return parts;
}

/**
 * 解析模型 capabilities（逗号分隔小写，如 "vision,tools"）：
 * - 含 vision → true；
 * - 未配置（空）→ null（与后端口径一致：放行 + Warning，不阻断存量模型）；
 * - 配置但无 vision → false。
 */
export function supportsVision(capabilities?: string | null): boolean | null {
	if (!capabilities || !capabilities.trim()) {
		return null;
	}
	const list = capabilities
		.toLowerCase()
		.split(',')
		.map(c => c.trim())
		.filter(Boolean);
	return list.includes('vision');
}
