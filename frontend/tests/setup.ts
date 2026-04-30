import { beforeEach, vi } from 'vitest';
import { setActivePinia, createPinia } from 'pinia';

const storage = new Map<string, string>();

Object.defineProperty(window, 'localStorage', {
	value: {
		getItem: vi.fn((key: string) => storage.get(key) ?? null),
		setItem: vi.fn((key: string, value: string) => storage.set(key, value)),
		removeItem: vi.fn((key: string) => storage.delete(key)),
		clear: vi.fn(() => storage.clear())
	},
	writable: true
});

Object.defineProperty(window, 'sessionStorage', {
	value: {
		getItem: vi.fn((key: string) => storage.get(key) ?? null),
		setItem: vi.fn((key: string, value: string) => storage.set(key, value)),
		removeItem: vi.fn((key: string) => storage.delete(key)),
		clear: vi.fn(() => storage.clear())
	},
	writable: true
});

beforeEach(() => {
	storage.clear();
	setActivePinia(createPinia());
});
