/**
 * E1 生成中草稿缓冲：generation_id 分桶 + seq 单调去重。
 *
 * - 跨响应（不同 generationId）互不混淆——新 generation 自动重开桶；
 * - 重复/迟到帧（seq ≤ 已见最大值）丢弃——断线重放不污染草稿；
 * - answer_reset 仅撤销当前桶（服务端同步撤销的镜像：该响应实为工具决策）。
 */
export class AnswerDraftBuffer {
	private generationId: string | null = null;
	private seq = 0;

	text = '';

	applyDelta(generationId: string, delta: string, seq: number): void {
		if (!generationId || !delta) return;
		if (generationId !== this.generationId) {
			this.generationId = generationId;
			this.seq = 0;
			this.text = '';
		}
		if (seq <= this.seq) return;
		this.seq = seq;
		this.text += delta;
	}

	/** 服务端撤销：仅当前桶命中时清空（他响应的 reset 与本桶无关）。 */
	reset(generationId: string): void {
		if (generationId === this.generationId) {
			this.text = '';
		}
	}

	/** 终态/新请求：整桶失效。 */
	clear(): void {
		this.generationId = null;
		this.seq = 0;
		this.text = '';
	}
}
