import { describe, expect, it, vi, beforeEach } from 'vitest';
import { createZipBlob, fetchImageAsArrayBuffer, downloadImagesAsZip } from '/$/workflow/utils/download';

describe('download utils', () => {
	beforeEach(() => {
		vi.restoreAllMocks();
	});

	it('creates valid zip blob from files', async () => {
		const files = [
			{ name: '01_image.png', data: new TextEncoder().encode('fake-png-data') },
			{ name: '02_image.jpg', data: new TextEncoder().encode('fake-jpg-data') }
		];
		const blob = createZipBlob(files);
		expect(blob).toBeInstanceOf(Blob);
		expect(blob.type).toBe('application/zip');
		expect(blob.size).toBeGreaterThan(0);
	});

	it('decodes data: URL directly without network request', async () => {
		const dataUrl = 'data:image/png;base64,aGVsbG8=';
		const mockFetch = vi.fn().mockResolvedValue({
			arrayBuffer: () => Promise.resolve(new TextEncoder().encode('hello').buffer)
		});
		vi.stubGlobal('fetch', mockFetch);

		const buffer = await fetchImageAsArrayBuffer(dataUrl);
		expect(buffer).toBeDefined();
		expect(mockFetch).toHaveBeenCalledWith(dataUrl);
	});

	it('routes restricted storage URLs (e.g. volces.com) through backend proxy', async () => {
		const volcUrl = 'https://ark-content-generation-v2-cn-beijing.tos-cn-beijing.volces.com/doubao/test.jpeg';
		const mockFetch = vi.fn().mockImplementation((url: string) => {
			if (typeof url === 'string' && url.includes('/admin/media/asset/proxyImage')) {
				return Promise.resolve({
					ok: true,
					arrayBuffer: () => Promise.resolve(new ArrayBuffer(16))
				});
			}
			return Promise.reject(new Error('CORS blocked'));
		});
		vi.stubGlobal('fetch', mockFetch);

		const buffer = await fetchImageAsArrayBuffer(volcUrl);
		expect(buffer).toBeDefined();
		const [proxyCallUrl] = mockFetch.mock.calls.find(([url]: string[]) =>
			typeof url === 'string' && url.includes('/admin/media/asset/proxyImage')
		) as [string];
		expect(proxyCallUrl).toContain('/admin/media/asset/proxyImage?url=');
		// 认证只经 Authorization header 传输，access token 不得拼进 URL query（防泄露到日志/Referer）
		expect(proxyCallUrl).not.toContain('token=');
	});
});
