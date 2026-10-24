/**
 * agent locale 消息可编译门禁（E1 期实战补缺：{{USER_NAME}} 字面量被 vue-i18n
 * 误判为嵌套占位符——parity 门禁只锁键集合，vitest 又不走 vite 的 unplugin 预编译，
 * 编译期错误只在 dev server 爆出）。用 @intlify/message-compiler 与 vite 同口径校验。
 *
 * 范围：仅 agent 模块（盲区首次暴露处）；其他模块若有同类问题再扩入。
 * 转义约定：字面量双花括号写 `{'{{'}` 与 `{'}'}`（vue-i18n literal interpolation）。
 */
import { readFileSync } from 'node:fs';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { baseCompile, type CompileError } from '@intlify/message-compiler';
import { describe, expect, it } from 'vitest';

const here = dirname(fileURLToPath(import.meta.url));
const localesDir = resolve(here, '../../../src/modules/agent/locales');

describe('agent locale 消息可编译', () => {
	for (const locale of ['zh-cn', 'en', 'zh-tw']) {
		it(`${locale} 全部消息可被 vue-i18n message compiler 解析`, () => {
			const data = JSON.parse(readFileSync(resolve(localesDir, `${locale}.json`), 'utf-8'));
			const bad: string[] = [];
			for (const [key, message] of Object.entries(data)) {
				let err: CompileError | null = null;
				baseCompile(message, {
					location: false,
					onError: (e: CompileError) => {
						err = e;
					}
				});
				if (err) bad.push(`${key}: ${err.message ?? err.code}`);
			}
			expect(bad, `不可编译消息:\n${bad.join('\n')}`).toEqual([]);
		});
	}
});
