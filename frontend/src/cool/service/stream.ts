import { useBase } from '/$/base';
import { config } from '/@/config';

export function useStream() {
	const { user } = useBase();
	let abortController: AbortController | null = null;
	// 是否已主动取消：用于吞掉 abort 引发的 reader.read() 拒绝，避免 Uncaught (in promise)
	let cancelled = false;

	// 调用
	async function invoke({
		url,
		method = 'POST',
		data,
		cb
	}: {
		url: string;
		method?: string;
		data?: any;
		cb?: (result: any) => void;
	}) {
		abortController = new AbortController();
		cancelled = false;

		let cacheText = '';

		return fetch(config.baseUrl + url, {
			method,
			headers: {
				Authorization: user.token,
				'Content-Type': 'application/json'
			},
			body: JSON.stringify(data),
			signal: abortController?.signal
		})
			.then(res => {
				if (res.body) {
					const reader = res.body.getReader();
					const decoder = new TextDecoder('utf-8');
					const stream = new ReadableStream({
						start(controller) {
							function push() {
								reader.read().then(({ done, value }) => {
									if (done || cancelled) {
										if (!cancelled) controller.close();
										return;
									}

									const text = decoder.decode(value, { stream: true });

									if (cb) {
										const parsed = parseSse(cacheText + text);
										parsed.events.forEach(cb);
										cacheText = parsed.rest;
									}

									// cb 可能在 forEach 中触发 cancel()，此时停止后续写入与递归
									if (cancelled) return;

									controller.enqueue(text);
									push();
								}).catch(err => {
									// 主动 cancel() 会 abort fetch，导致 reader.read() 以 AbortError 拒绝，属预期，静默
									if (cancelled || err?.name === 'AbortError') return;
									console.error(err);
								});
							}
							push();
						}
					});

					return new Response(stream);
				}

				return res;
			})
			.catch(err => {
				console.error(err);
				throw err;
			});
	}

	// 取消
	function cancel() {
		cancelled = true;
		if (abortController) {
			abortController.abort();
			abortController = null;
		}
	}

	return {
		invoke,
		cancel
	};
}

function parseSse(text: string) {
	const events: any[] = [];
	const normalized = text.replace(/\r\n/g, '\n');
	const parts = normalized.split('\n\n');
	const rest = parts.pop() || '';

	for (const part of parts) {
		const data: string[] = [];

		for (const line of part.split('\n')) {
			if (!line || line.startsWith(':') || line.startsWith('event:')) {
				continue;
			}

			if (line.startsWith('data:')) {
				data.push(line.slice(5).trimStart());
			}
		}

		const value = data.join('\n').trim();

		if (!value) {
			continue;
		}

		try {
			events.push(JSON.parse(value));
		} catch (err) {
			console.error('[parse sse]', value);
		}
	}

	return { events, rest };
}
