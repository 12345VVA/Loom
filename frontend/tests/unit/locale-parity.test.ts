/**
 * locale 三语一致性门禁（WFU 根因三：i18n 缺失靠人肉记忆，无 CI 拦截）。
 *
 * 规则：src/modules 下各模块 locales/ 目录以 zh-cn 为基准，en / zh-tw 的
 * key 集合必须与其完全一致（缺失 = 切换语言回退中文；孤儿 = 死文案）。
 *
 * 约束（2026-10 实况）：
 * - zh-cn 恒等映射（中文串即 key），新增 UI 文案时三份同步补；
 * - vitest 环境 i18n messages 被 mock 为空，运行时比对不可行，故直读 JSON；
 * - 代码里 $t() 引用但 zh-cn 缺失的 key 不在本门禁范围（回退显示原中文，
 *   由批次清偿；此门禁只锁三份文件间的漂移）。
 */
import { existsSync, readdirSync, readFileSync } from 'node:fs';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { describe, expect, it } from 'vitest';

const here = dirname(fileURLToPath(import.meta.url));
const modulesDir = resolve(here, '../../src/modules');

interface LocaleFile {
	module: string;
	locale: string;
	keys: string[];
}

function loadLocaleFiles(): LocaleFile[] {
	const files: LocaleFile[] = [];
	for (const module of readdirSync(modulesDir)) {
		const localesDir = resolve(modulesDir, module, 'locales');
		if (!existsSync(localesDir)) continue;
		for (const fn of readdirSync(localesDir)) {
			const m = fn.match(/^(zh-cn|en|zh-tw)\.json$/);
			if (!m) continue;
			const data = JSON.parse(readFileSync(resolve(localesDir, fn), 'utf-8'));
			files.push({ module, locale: m[1], keys: Object.keys(data) });
		}
	}
	return files;
}

describe('locale 三语一致性门禁', () => {
	const files = loadLocaleFiles();
	const byModule = new Map<string, Map<string, string[]>>();
	for (const f of files) {
		if (!byModule.has(f.module)) byModule.set(f.module, new Map());
		byModule.get(f.module)!.set(f.locale, f.keys);
	}

	it('各模块三语文件齐备', () => {
		expect(files.length).toBeGreaterThan(0);
		for (const [module, locales] of byModule) {
			for (const locale of ['zh-cn', 'en', 'zh-tw']) {
				expect(locales.has(locale), `${module} 缺 ${locale}.json`).toBe(true);
			}
		}
	});

	for (const [module, locales] of byModule) {
		const base = new Set(locales.get('zh-cn') ?? []);
		for (const locale of ['en', 'zh-tw']) {
			it(`${module}/${locale}：无缺失、无孤儿 key`, () => {
				const other = locales.get(locale) ?? [];
				const missing = [...base].filter(k => !other.includes(k));
				const orphan = other.filter(k => !base.has(k));
				expect(missing, `${module}/${locale} 缺失 key（切换语言将回退中文）`).toEqual([]);
				expect(orphan, `${module}/${locale} 孤儿 key（死文案）`).toEqual([]);
			});
		}
	}
});
