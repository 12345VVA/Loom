/**
 * EPS 生成链守卫（规范见 .cursor/rules/eps-dts-generation.mdc）。
 *
 * 防两类回归：
 * 1. 入库基线 eps.d.ts 被官方版插件重新生成覆盖（脏格式指纹：_action_name 回流、
 *    POST data 收窄、具名 Response 消失——2026-10-06 曾致 type-check 假报 10 错）
 * 2. node_modules 安装态意外回退 registry tarball（workspaces junction 断裂）
 */
import { readFileSync, realpathSync } from 'node:fs';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { createRequire } from 'node:module';
import { describe, expect, it } from 'vitest';

const here = dirname(fileURLToPath(import.meta.url));
const epsPath = resolve(here, '../../build/cool/eps.d.ts');

describe('eps-baseline 守卫', () => {
	const dts = readFileSync(epsPath, 'utf-8');

	it('不含 _action_name 噪音参数（官方版生成器指纹）', () => {
		expect(dts).not.toContain('_action_name');
	});

	it('保留 POST data?: any + 具名 Response 签名（B3 泛型化特征）', () => {
		expect(dts).toMatch(/add\(data\?: any\): Promise<\w+Response>/);
	});

	it('实体索引签名 / DictKey / 新字段在位', () => {
		expect(dts).toContain('[key: string]: any');
		expect(dts).toMatch(/type DictKey = /);
		expect(dts).toContain('runType');
	});

	it('安装副本是 workspace junction 且 dist 为定制版', () => {
		const require = createRequire(import.meta.url);
		const entry = require.resolve('@cool-vue/vite-plugin');
		// junction 断裂（range 失配回退 registry 等）时 realpath 会落在 node_modules 实体目录
		const real = realpathSync(entry).replace(/\\/g, '/');
		expect(real).toContain('/packages/vite-plugin/');
		// 生成器定制指纹在 eps 子模块：顶层对象提升为具名 Response 接口（官方 8.2.20 无此逻辑）
		const epsModule = readFileSync(resolve(dirname(entry), 'eps/index.js'), 'utf-8');
		expect(epsModule).toContain('${name}PageResponse');
	});
});
