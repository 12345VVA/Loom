import { describe, expect, it, vi, beforeEach } from 'vitest';

import { useTestForm } from '/$/workflow/composables/use-test-form';

const requestMock = vi.fn().mockResolvedValue({ id: 1, url: '/uploads/2026/10/a.png', name: 'a.png' });

function makeForm() {
	const service = {
		media: {
			asset: {
				request: requestMock
			}
		}
	};
	const t = (s: string) => s;
	return useTestForm(service as Parameters<typeof useTestForm>[0], t);
}

describe('useTestForm（WFI-1c 试运行可视化表单）', () => {
	beforeEach(() => {
		requestMock.mockClear();
		requestMock.mockResolvedValue({ id: 1, url: '/uploads/2026/10/a.png', name: 'a.png' });
	});

	it('未声明变量时表单模式不可用（维持 JSON 模式老行为）', () => {
		const form = makeForm();
		expect(form.formAvailable.value).toBe(false);
		form.initFromVariables([], null);
		expect(form.formAvailable.value).toBe(false);
	});

	it('按类型产初值：image→空串、number→0、boolean→false', () => {
		const form = makeForm();
		form.initFromVariables(
			[
				{ name: 'input_image', type: 'image' },
				{ name: 'count', type: 'number' },
				{ name: 'flag', type: 'boolean' }
			],
			[{ name: 'input_image', type: 'image' }, { name: 'count', type: 'number' }, { name: 'flag', type: 'boolean' }]
		);
		expect(form.values.value).toEqual({ input_image: '', count: 0, flag: false });
		expect(form.mode.value).toBe('form');
	});

	it('start 声明的默认值优先于类型初值，initial 回填优先于默认值', () => {
		const form = makeForm();
		form.initFromVariables([{ name: 'count', type: 'number' }], [{ name: 'count', default: 10 }]);
		expect(form.values.value.count).toBe(10);
		form.initFromVariables([{ name: 'count', type: 'number' }], [{ name: 'count', default: 10 }], { count: 7 });
		expect(form.values.value.count).toBe(7);
	});

	it('toJson/fromJson 双向同步；非法 JSON 返回 false', () => {
		const form = makeForm();
		form.initFromVariables([{ name: 'q', type: 'string' }], null, { q: '你好' });
		const json = form.toJson();
		expect(JSON.parse(json)).toEqual({ q: '你好' });

		form.values.value.q = '改了';
		expect(form.fromJson(json)).toBe(true);
		expect(form.values.value.q).toBe('你好');
		expect(form.fromJson('{bad json')).toBe(false);
	});

	it('uploadImage 经媒体上传接口回填相对 URL', async () => {
		const form = makeForm();
		form.initFromVariables([{ name: 'img', type: 'image' }], null);
		await form.uploadImage('img', new File([new Uint8Array([1])], 'a.png', { type: 'image/png' }));
		expect(requestMock).toHaveBeenCalledTimes(1);
		const args = requestMock.mock.calls[0][0];
		expect(args.url).toBe('/upload');
		expect(args.method).toBe('POST');
		expect(args.data).toBeInstanceOf(FormData);
		expect(form.values.value.img).toBe('/uploads/2026/10/a.png');
	});

	it('uploadImage 接口未返回 url 时不回填', async () => {
		requestMock.mockResolvedValueOnce({ id: 2 });
		const form = makeForm();
		form.initFromVariables([{ name: 'img', type: 'image' }], null);
		await form.uploadImage('img', new File([new Uint8Array([1])], 'a.png', { type: 'image/png' }));
		expect(form.values.value.img).toBe('');
	});

	it('validate：required 缺失与 data: 前缀拦截，合法值放行', () => {
		const form = makeForm();
		form.initFromVariables(
			[
				{ name: 'must', type: 'string', required: true },
				{ name: 'img', type: 'image' }
			],
			null,
			{ must: '', img: '' }
		);
		expect(form.validate()).toContain('must');

		form.values.value.must = '有值';
		form.values.value.img = 'data:image/png;base64,xxx';
		expect(form.validate()).toContain('Base64');

		form.values.value.img = '/uploads/a.png';
		expect(form.validate()).toBeNull();
	});

	it('list 值内混入 data URI 同样被拦截', () => {
		const form = makeForm();
		form.initFromVariables([{ name: 'imgs', type: 'string' }], null, {
			imgs: ['https://x/1.jpg', 'data:image/png;base64,y']
		});
		expect(form.validate()).toContain('Base64');
	});

	it('getInputs：校验失败返回 null，成功返回值副本', () => {
		const form = makeForm();
		form.initFromVariables([{ name: 'img', type: 'image' }], null, { img: 'data:image/png;base64,z' });
		expect(form.getInputs()).toBeNull();

		form.values.value.img = '/uploads/b.png';
		const inputs = form.getInputs();
		expect(inputs).toEqual({ img: '/uploads/b.png' });
		// 副本语义：外部改 inputs 不影响表单
		inputs!.img = 'changed';
		expect(form.values.value.img).toBe('/uploads/b.png');
	});
});
