import { describe, expect, it, vi } from 'vitest';
import { request } from '/@/cool/service/request';

const mocks = vi.hoisted(() => ({
	logout: vi.fn(),
	push: vi.fn()
}));

vi.mock('nprogress', () => ({
	default: {
		configure: vi.fn(),
		start: vi.fn(),
		done: vi.fn()
	}
}));

vi.mock('element-plus', () => ({
	ElMessage: {
		error: vi.fn()
	}
}));

vi.mock('/$/base', () => ({
	useBase: () => ({
		user: {
			token: '',
			logout: mocks.logout,
			refreshToken: vi.fn()
		}
	})
}));

vi.mock('/@/cool/utils', () => ({
	storage: {
		isExpired: vi.fn(() => false)
	}
}));

vi.mock('/@/config', () => ({
	config: {
		ignore: {
			NProgress: []
		},
		i18n: {
			locale: 'zh-cn'
		}
	},
	isDev: false
}));

vi.mock('/@/cool/router', () => ({
	router: {
		push: mocks.push
	}
}));

describe('request interceptors', () => {
	it('unwraps success envelopes and rejects business errors', async () => {
		const success = await request.interceptors.response.handlers[0].fulfilled({
			data: {
				code: 1000,
				data: { ok: true },
				message: 'success'
			}
		});

		await expect(
			request.interceptors.response.handlers[0].fulfilled({
				data: {
					code: 4000,
					message: 'bad request'
				}
			})
		).rejects.toEqual({ code: 4000, message: 'bad request' });
		expect(success).toEqual({ ok: true });
	});

	it('logs out on 401 and routes server errors in production mode', async () => {
		await expect(
			request.interceptors.response.handlers[0].rejected({
				response: {
					status: 401,
					data: { message: 'unauthorized' }
				}
			})
		).rejects.toEqual({ message: 'unauthorized' });
		expect(mocks.logout).toHaveBeenCalled();

		await expect(
			request.interceptors.response.handlers[0].rejected({
				response: {
					status: 500,
					data: { message: 'server error' }
				}
			})
		).rejects.toEqual({ message: 'server error' });
		expect(mocks.push).toHaveBeenCalledWith('/500');
	});
});
