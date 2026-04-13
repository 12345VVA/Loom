import { readFileSync, readdirSync } from "fs";
import { basename, extname } from "path";
import { rootDir } from "../utils";
import svgo from "svgo";
import { config } from "../config";

let svgIcons: string[] = [];

function findSvg(dir: string) {
	const arr: string[] = [];
	const dirs = readdirSync(dir, {
		withFileTypes: true,
	});

	// 获取当前目录的模块名
	const moduleName = dir.match(/[/\\](?:src[/\\](?:plugins|modules)[/\\])([^/\\]+)/)?.[1] || "";

	for (const d of dirs) {
		if (d.isDirectory()) {
			arr.push(...findSvg(dir + d.name + "/"));
		} else {
			if (extname(d.name) == ".svg") {
				const baseName = basename(d.name, ".svg");

				// 判断是否需要跳过拼接模块名
				let shouldSkip = config.svg.skipNames?.includes(moduleName);

				// 跳过包含icon-
				if (baseName.includes("icon-")) {
					shouldSkip = true;
				}

				const iconName = shouldSkip ? baseName : `${moduleName}-${baseName}`;

				svgIcons.push(iconName);

				const svg = readFileSync(dir + d.name)
					.toString()
					.replace(/(\r)|(\n)/g, "")
					.replace(/<svg([^>+].*?)>/, (_: any, $2: any) => {
						let width = 0;
						let height = 0;
						let content = $2.replace(
							/(width|height)="([^>+].*?)"/g,
							(_: any, s2: any, s3: any) => {
								if (s2 === "width") {
									width = s3;
								} else if (s2 === "height") {
									height = s3;
								}
								return "";
							},
						);
						if (!/(viewBox="[^>+].*?")/g.test($2)) {
							content += `viewBox="0 0 ${width} ${height}"`;
						}
						return `<symbol id="icon-${iconName}" ${content}>`;
					})
					.replace("</svg>", "</symbol>");

				arr.push(svg);
			}
		}
	}

	return arr;
}

function compilerSvg() {
	svgIcons = [];

	return findSvg(rootDir("./src/"))
		.map((e) => {
			return svgo.optimize(e)?.data || e;
		})
		.join("");
}

export async function createSvg() {
	const html = compilerSvg();

	const code = `
if (typeof window !== 'undefined') {
	function loadSvg() {
		const svgDom = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
		svgDom.style.position = 'absolute';
		svgDom.style.width = '0';
		svgDom.style.height = '0';
		svgDom.setAttribute('xmlns','http://www.w3.org/2000/svg');
		svgDom.setAttribute('xmlns:link','http://www.w3.org/1999/xlink');
		svgDom.innerHTML = '${html}';
		document.body.insertBefore(svgDom, document.body.firstChild);
	}

	loadSvg();
}
		`;

	return { code, svgIcons };
}
