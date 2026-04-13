import { createWriteStream } from "fs";
import { join } from "path";
import { createDir, formatContent } from "../utils";
import { isArray } from "lodash";

interface Item {
	path: string;
	code: string;
}

// 创建文件
export async function createFile(data: Item | Item[]) {
	const list = isArray(data) ? data : [data];

	for (const item of list) {
		const { path, code } = item;

		// 格式化内容
		const content = await formatContent(code, {
			parser: "vue",
		});

		// 目录路径
		const dir = (path || "").split("/");

		// 文件名
		const fname = dir.pop();

		// 源码路径
		const srcPath = `./src/${dir.join("/")}`;

		// 创建目录
		createDir(srcPath, true);

		// 创建文件
		createWriteStream(join(srcPath, fname!), {
			flags: "w",
		}).write(content);
	}
}
