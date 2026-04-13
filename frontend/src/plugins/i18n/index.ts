import messages from '@intlify/unplugin-vue-i18n/messages';
import { config } from '/@/config';

export const t = (key: string, params?: Record<string, string>) => {
	const language = config.i18n.locale;

	// @ts-ignore
	const message: string = messages?.[language]?.[key]?.loc?.source || key;

	// 参数插值
	if (params) {
		return message.replace(/\{(\w+)\}/g, (_, param) => params[param] || `{${param}}`);
	}

	return message;
};
