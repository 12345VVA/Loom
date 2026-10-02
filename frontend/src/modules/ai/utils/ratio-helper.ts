/**
 * 生图尺寸与比例匹配计算工具函数
 */

export interface AspectRatioItem {
	key: string;
	label: string;
	iconClass: string;
}

export const COMMON_RATIOS: AspectRatioItem[] = [
	{ key: '1:1', label: '1:1 方形', iconClass: 'icon-square' },
	{ key: '16:9', label: '16:9 电脑横屏', iconClass: 'icon-landscape' },
	{ key: '9:16', label: '9:16 手机竖屏', iconClass: 'icon-portrait' },
	{ key: '4:3', label: '4:3 标准横向', iconClass: 'icon-standard-h' },
	{ key: '3:4', label: '3:4 经典竖向', iconClass: 'icon-standard-v' }
];

const TARGET_RATIO_VALUES: Record<string, number> = {
	'1:1': 1.0,
	'16:9': 16 / 9,
	'9:16': 9 / 16,
	'4:3': 4 / 3,
	'3:4': 3 / 4
};

/**
 * 判断当前尺寸是否与指定比例匹配
 */
export function isRatioActive(currentSize: string | undefined | null, ratioKey: string): boolean {
	if (!currentSize) return false;
	const curSize = String(currentSize).toLowerCase();
	if (curSize === ratioKey.toLowerCase()) {
		return true;
	}
	// 百炼/火山等显式尺寸：包含比例说明，如 1280x720(16:9)
	if (curSize.includes(ratioKey)) {
		return true;
	}
	// 尺寸解析宽高比匹配 (容差计算)
	const [w, h] = curSize.split('x').map(Number);
	if (w && h) {
		const ratio = (w / h).toFixed(2);
		if (ratioKey === '1:1' && ratio === '1.00') return true;
		if (ratioKey === '16:9' && (ratio === '1.78' || ratio === '1.75')) return true;
		if (ratioKey === '9:16' && (ratio === '0.56' || ratio === '0.57')) return true;
		if (ratioKey === '4:3' && ratio === '1.33') return true;
		if (ratioKey === '3:4' && ratio === '0.75') return true;
	}
	return false;
}

/**
 * 选中比例，自动从当前可用尺寸列表中选出最匹配的尺寸值
 */
export function selectBestRatioSize(
	options: Array<{ label: string; value: string }>,
	ratioKey: string
): string | null {
	if (!options || options.length === 0) return null;

	// 1. 优先完全相等 (如 ToAPIs 的 "1:1", "16:9")
	const exact = options.find(opt => opt.value === ratioKey);
	if (exact) {
		return exact.value;
	}

	// 2. 查找 label 或 value 包含该比例字符串的选项
	const foundByLabel = options.find(
		opt => opt.label.includes(ratioKey) || opt.value.includes(ratioKey)
	);
	if (foundByLabel) {
		return foundByLabel.value;
	}

	// 3. 计算宽高比例数值差寻找最接近项
	const target = TARGET_RATIO_VALUES[ratioKey];
	if (target) {
		let bestOption = options[0];
		let minDiff = Infinity;
		for (const opt of options) {
			const [w, h] = opt.value.split('x').map(Number);
			if (w && h) {
				const diff = Math.abs(w / h - target);
				if (diff < minDiff) {
					minDiff = diff;
					bestOption = opt;
				}
			}
		}
		return bestOption.value;
	}

	return options[0]?.value || null;
}
