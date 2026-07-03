import { checkPerm } from '../utils/permission';

// 原生支持 disabled 属性的可交互元素，优先通过 disabled 禁用
const DISABLEABLE_TAGS = new Set(['BUTTON', 'INPUT', 'SELECT', 'TEXTAREA']);

// 应用无权限状态：隐藏 + 禁用交互 + 无障碍标记
function disable(el: HTMLElement) {
	// 已应用过则跳过，避免覆盖已保存的原始值
	if (el.hasAttribute('_noperm')) return;
	el.setAttribute('_noperm', '1');
	// 备份原始样式
	el.setAttribute('_display', el.style.display || '');
	el.setAttribute('_pe', el.style.pointerEvents || '');
	// 隐藏元素
	el.style.display = 'none';
	// 阻止交互：可交互元素用 disabled 原生禁用，其他元素用 pointer-events
	if (DISABLEABLE_TAGS.has(el.tagName)) {
		el.setAttribute('_disabled', (el as any).disabled ? '1' : '0');
		(el as any).disabled = true;
	} else {
		el.style.pointerEvents = 'none';
	}
	// 无障碍标记
	el.setAttribute('aria-hidden', 'true');
}

// 恢复权限：清除全部无权限标记并还原原始样式
function restore(el: HTMLElement) {
	if (!el.hasAttribute('_noperm')) return;
	el.removeAttribute('_noperm');
	el.style.display = el.getAttribute('_display') || '';
	el.removeAttribute('_display');
	el.style.pointerEvents = el.getAttribute('_pe') || '';
	el.removeAttribute('_pe');
	if (el.hasAttribute('_disabled')) {
		(el as any).disabled = el.getAttribute('_disabled') === '1';
		el.removeAttribute('_disabled');
	}
	el.removeAttribute('aria-hidden');
}

function change(el: HTMLElement, binding: { value: any }) {
	if (checkPerm(binding.value)) {
		restore(el);
	} else {
		disable(el);
	}
}

export default {
	created(el: HTMLElement, binding: { value: any }) {
		change(el, binding);
	},
	updated: change
};
