import { base } from "./base";
import { config } from "./config";
import { demo } from "./demo";
import { getProxyTarget } from "./proxy";
import type { Config } from "../types";
import { virtual } from "./virtual";
import { assign, merge } from "lodash";
import { uniappX } from "./uniapp-x";

export function cool(options: Config.Options) {
	// 应用类型，admin | app
	config.type = options.type;

	// 请求地址
	config.reqUrl = getProxyTarget(options.proxy);

	if (config.type == "uniapp-x") {
		// 编译平台
		config.utsPlatform = process.env.UNI_UTS_PLATFORM ?? "web";

		// 是否纯净版
		config.clean = options.clean ?? true;

		if (config.clean) {
			// 默认设置为测试地址
			config.reqUrl = "https://show.cool-admin.com/api";
		}
	}

	// 是否开启名称标签
	config.nameTag = options.nameTag ?? true;

	// svg
	if (options.svg) {
		assign(config.svg, options.svg);
	}

	// Eps
	if (options.eps) {
		const { dist, mapping, api, enable = true } = options.eps;

		// 是否开启
		config.eps.enable = enable;

		// 类型
		if (api) {
			config.eps.api = api;
		}

		// 输出目录
		if (dist) {
			config.eps.dist = dist;
		}

		// 匹配规则
		if (mapping) {
			merge(config.eps.mapping, mapping);
		}
	}

	// 如果类型为 uniapp-x，则关闭 eps
	if (config.type == "uniapp-x") {
		config.eps.enable = false;
	}

	// uniapp
	if (options.uniapp) {
		assign(config.uniapp, options.uniapp);
	}

	// tailwind
	if (options.tailwind) {
		assign(config.tailwind, options.tailwind);
	}

	return [base(), virtual(), uniappX(), demo(options.demo)];
}
