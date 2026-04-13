import { error, readFile, rootDir, writeFile } from "../utils";
import { config } from "../config";

function getPath() {
	return rootDir(`.${config.type == "admin" ? "/src" : ""}/config/proxy.ts`);
}

export async function updateProxy(data: { name: string }) {
	let code = readFile(getPath());

	const regex = /const\s+value\s*=\s*['"]([^'"]+)['"]/;
	if (regex.test(code)) {
		code = code.replace(regex, `const value = '${data.name}'`);
	}

	writeFile(getPath(), code);
}

export function getProxyTarget(proxy: any) {
	const code = readFile(getPath());

	const regex = /const\s+value\s*=\s*['"]([^'"]+)['"]/;
	const match = code.match(regex);

	if (match) {
		const value = match[1];

		try {
			const { target, rewrite } = proxy[`/${value}/`];
			return target + rewrite(`/${value}`);
		} catch (err) {
			error(`[cool-proxy] Error：${value} → ` + getPath());
			return "";
		}
	}
}
