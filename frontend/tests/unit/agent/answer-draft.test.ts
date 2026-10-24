import { describe, expect, it } from 'vitest';
import { AnswerDraftBuffer } from '/$/agent/utils/answer-draft';

describe('agent/utils/answer-draft', () => {
	it('同 generation 增量按 seq 顺序累积', () => {
		const buf = new AnswerDraftBuffer();
		buf.applyDelta('g1', '你好', 1);
		buf.applyDelta('g1', '，世界', 2);
		expect(buf.text).toBe('你好，世界');
	});

	it('seq 重复/迟到帧丢弃（断线重放不污染，A23）', () => {
		const buf = new AnswerDraftBuffer();
		buf.applyDelta('g1', 'A', 1);
		buf.applyDelta('g1', 'B', 2);
		buf.applyDelta('g1', 'B', 2); // 重放
		buf.applyDelta('g1', 'A', 1); // 迟到
		expect(buf.text).toBe('AB');
	});

	it('跨 generation 分桶：新 generation 重开桶（E1）', () => {
		const buf = new AnswerDraftBuffer();
		buf.applyDelta('g1', '第一轮草稿', 1);
		buf.applyDelta('g2', '第二轮', 1);
		expect(buf.text).toBe('第二轮');
	});

	it('reset 仅命中当前桶（他响应的 reset 不误清）', () => {
		const buf = new AnswerDraftBuffer();
		buf.applyDelta('g1', '草稿', 1);
		buf.reset('g-other');
		expect(buf.text).toBe('草稿');
		buf.reset('g1');
		expect(buf.text).toBe('');
	});

	it('reset 后同桶新 delta 重新累积', () => {
		const buf = new AnswerDraftBuffer();
		buf.applyDelta('g1', '被撤销', 1);
		buf.reset('g1');
		buf.applyDelta('g1', '新内容', 2);
		expect(buf.text).toBe('新内容');
	});

	it('clear 后新 generation 从零开始', () => {
		const buf = new AnswerDraftBuffer();
		buf.applyDelta('g1', '旧', 1);
		buf.clear();
		buf.applyDelta('g2', '新', 1);
		expect(buf.text).toBe('新');
	});

	it('空 delta / 空 generationId 忽略', () => {
		const buf = new AnswerDraftBuffer();
		buf.applyDelta('g1', '', 1);
		buf.applyDelta('', 'x', 1);
		expect(buf.text).toBe('');
	});
});
