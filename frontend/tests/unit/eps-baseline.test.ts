/**
 * EPS 生成链守卫（规范见 .cursor/rules/eps-dts-generation.mdc）。
 *
 * 防四类回归：
 * 1. 入库基线 eps.d.ts 被官方版插件重新生成覆盖（脏格式指纹：_action_name 回流、
 *    POST data 收窄、具名 Response 消失——2026-10-06 曾致 type-check 假报 10 错）
 * 2. node_modules 安装态意外回退 registry tarball（workspaces junction 断裂）
 * 3. 迁移期"自洽降级态"：eps.json 与 eps.d.ts 互相一致但都是降级版
 *    （summary 丢失 / DictKey 退化为裸 string）——diff 门禁测不出一致地坏
 * 4. 跨库漂移：改了后端接口只更新 eps_baseline.json、前端 eps.json/eps.d.ts 漏同步
 */
import { readFileSync, realpathSync } from 'node:fs';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { createRequire } from 'node:module';
import { describe, expect, it } from 'vitest';

const here = dirname(fileURLToPath(import.meta.url));
const epsPath = resolve(here, '../../build/cool/eps.d.ts');
const epsJsonPath = resolve(here, '../../build/cool/eps.json');
const baselinePath = resolve(here, '../../../backend/eps_baseline.json');

interface EpsApiItem {
	method?: string;
	path: string;
	summary?: string;
}

interface EpsEntity {
	prefix: string;
	api?: EpsApiItem[];
}

interface EpsJsonFile {
	list: EpsEntity[];
	dictTypes: string[];
}

const epsJson: EpsJsonFile = JSON.parse(readFileSync(epsJsonPath, 'utf-8'));
const baseline: Record<string, EpsEntity[]> = JSON.parse(readFileSync(baselinePath, 'utf-8'));

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

describe('eps.json 确定性缓存守卫', () => {
	it('新格式 { list, dictTypes } 且均非空', () => {
		expect(Array.isArray(epsJson.list)).toBe(true);
		expect(epsJson.list.length).toBeGreaterThan(0);
		expect(Array.isArray(epsJson.dictTypes)).toBe(true);
		expect(epsJson.dictTypes.length).toBeGreaterThan(0);
	});

	it('api 项保留 summary（防迁移期自洽降级态：summary 丢失后重生成仍"一致地坏"）', () => {
		const withSummary = epsJson.list.some((e) => (e.api || []).some((a) => !!a.summary));
		expect(withSummary).toBe(true);
	});

	it('DictKey 未退化为裸 string（dictTypes 缓存在位并已渲染进 eps.d.ts）', () => {
		expect(readFileSync(epsPath, 'utf-8')).toMatch(/type DictKey = "/);
	});
});

describe('eps.json 与后端基线跨库语义一致（防只更新一侧的契约漂移）', () => {
	function apiSignature(entities: EpsEntity[]) {
		return new Map(
			entities.map(e => [
				e.prefix,
				(e.api || [])
					.map(a => `${(a.method || 'get').toLowerCase()}:${a.path}`)
					.sort()
			])
		);
	}

	const fe = apiSignature(epsJson.list);
	const be = apiSignature(Object.values(baseline).flat());

	it('实体 prefix 集合一致', () => {
		expect([...fe.keys()].sort()).toEqual([...be.keys()].sort());
	});

	it('每实体 api (method, path) 集合一致', () => {
		for (const [prefix, apis] of fe) {
			expect(be.get(prefix), `baseline 缺实体 ${prefix}`).toEqual(apis);
		}
	});
});
