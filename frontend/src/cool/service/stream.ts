import { useBase } from '/$/base';
import { config } from '/@/config';

export function useStream() {
	const { user } = useBase();
	let abortController: AbortController | null = null;

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
									if (done) {
										controller.close();
										return;
									}

									const text = decoder.decode(value, { stream: true });

									if (cb) {
										const parsed = parseSse(cacheText + text);
										parsed.events.forEach(cb);
										cacheText = parsed.rest;
									}

									controller.enqueue(text);
									push();
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
