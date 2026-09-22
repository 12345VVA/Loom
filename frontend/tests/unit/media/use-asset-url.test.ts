import { describe, expect, it, vi, beforeEach } from 'vitest';

vi.mock('/@/cool', () => ({
	useCool: () => ({
		service: {
			media: {
				asset: {
					downloadToken: vi.fn().mockResolvedValue({ token: 'mocked_token', expire: 7200 })
				}
			}
		}
	})
}));

import { useAssetUrl } from '/$/media/composables/use-asset-url';
import { config } from '/@/config';

describe('useAssetUrl', () => {
	beforeEach(() => {
		vi.restoreAllMocks();
	});

	it('returns empty string for falsy input', () => {
		const { assetUrl } = useAssetUrl();
		expect(assetUrl('')).toBe('');
		expect(assetUrl(undefined)).toBe('');
	});

	it('returns data: and blob: URLs untouched', () => {
		const { assetUrl } = useAssetUrl();
		const dataUrl = 'data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg==';
		const blobUrl = 'blob:http://localhost:9090/uuid-1234';
		expect(assetUrl(dataUrl)).toBe(dataUrl);
		expect(assetUrl(blobUrl)).toBe(blobUrl);
	});

	it('returns external remote URLs untouched (no baseUrl, no download token)', () => {
		const { assetUrl } = useAssetUrl();
		const tosUrl =
			'https://ark-content-generation-v2-cn-beijing.tos-cn-beijing.volces.com/doubao-seedream-4-5/0217898773915533d3436761e68cde6bd2815b0b11060ac645358_0.jpeg?X-Tos-Algorithm=TOS4-HMAC-SHA256';
		expect(assetUrl(tosUrl)).toBe(tosUrl);
	});

	it('normalizes local uploads paths idempotently and never produces double baseUrl', () => {
		const { assetUrl } = useAssetUrl();
		const base = config.baseUrl ? config.baseUrl.replace(/\/+$/, '') : '';
		const expectedPrefix = base ? `${base}/` : '/';
		const expectedClean = `${expectedPrefix}uploads/20260921/4f839e05d0e547bbaebac6d305d18260.png`;

		// 各类输入形式均应稳定归一化
		const r1 = assetUrl('/uploads/20260921/4f839e05d0e547bbaebac6d305d18260.png');
		const r2 = assetUrl('uploads/20260921/4f839e05d0e547bbaebac6d305d18260.png');
		const r3 = assetUrl('/dev/uploads/20260921/4f839e05d0e547bbaebac6d305d18260.png');
		const r4 = assetUrl('/dev/dev/uploads/20260921/4f839e05d0e547bbaebac6d305d18260.png');
		const r5 = assetUrl('http://localhost:9090/dev/uploads/20260921/4f839e05d0e547bbaebac6d305d18260.png');

		// 剥离 token 参数后检查路径
		const cleanR1 = r1.split('?')[0];
		const cleanR2 = r2.split('?')[0];
		const cleanR3 = r3.split('?')[0];
		const cleanR4 = r4.split('?')[0];
		const cleanR5 = r5.split('?')[0];

		expect(cleanR1).toBe(expectedClean);
		expect(cleanR2).toBe(expectedClean);
		expect(cleanR3).toBe(expectedClean);
		expect(cleanR4).toBe(expectedClean);
		expect(cleanR5).toBe(expectedClean);

		// 确保绝对不包含 /dev/dev/
		expect(r1).not.toContain('/dev/dev/');
		expect(r2).not.toContain('/dev/dev/');
		expect(r3).not.toContain('/dev/dev/');
		expect(r4).not.toContain('/dev/dev/');
		expect(r5).not.toContain('/dev/dev/');

		// 验证幂等性：连续多次调用输出恒定
		const idempotentR = assetUrl(assetUrl(assetUrl(r1)));
		expect(idempotentR.split('?')[0]).toBe(expectedClean);
		expect(idempotentR).not.toContain('/dev/dev/');
	});

	it('strips stale query tokens and injects fresh token', () => {
		const { assetUrl, downloadToken } = useAssetUrl();
		downloadToken.value = 'fresh_token_123';

		const urlWithStaleToken = '/dev/uploads/20260921/test.png?token=stale_old_token&foo=bar';
		const resolved = assetUrl(urlWithStaleToken);

		expect(resolved).toContain('token=fresh_token_123');
		expect(resolved).not.toContain('stale_old_token');
		expect(resolved).not.toContain('/dev/dev/');
	});
});
