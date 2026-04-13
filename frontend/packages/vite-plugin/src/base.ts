import type { Plugin } from "vite";
import { createEps } from "./eps";
import { parseJson } from "./utils";
import { updatePlugin } from "./plugin";
import { updateProxy } from "./proxy";
import { createFile } from "./file";
import { config } from "./config";
import { createTag } from "./tag";

export function base(): Plugin {
	return {
		name: "vite-cool-base",
		enforce: "pre",
		configureServer(server) {
			server.middlewares.use(async (req, res, next) => {
				function done(data: any) {
					res.writeHead(200, { "Content-Type": "text/html;charset=UTF-8" });
					res.end(JSON.stringify(data));
				}

				if (req.originalUrl?.includes("__cool")) {
					const body = await parseJson(req);

					switch (req.url) {
						// 创建文件
						case "/__cool_createFile":
							await createFile(body);
							break;

						// 创建 eps 文件
						case "/__cool_eps":
							await createEps();
							break;

						// 更新插件
						case "/__cool_updatePlugin":
							await updatePlugin(body);
							break;

						// 设置代理
						case "/__cool_updateProxy":
							await updateProxy(body);
							break;

						default:
							return done({
								code: 1001,
								message: "Unknown request",
							});
					}

					done({
						code: 1000,
					});
				} else {
					next();
				}
			});
		},
		transform(code, id) {
			if (config.nameTag) {
				return createTag(code, id);
			}

			return code;
		},
	};
}
