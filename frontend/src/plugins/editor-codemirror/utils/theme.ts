import { EditorView } from '@codemirror/view';

/**
 * Element Plus 风格浅色主题。
 * 所有颜色使用 CSS 变量，自动跟随主题色和暗色模式。
 */
export const elementPlusLightTheme = EditorView.theme({
	'&': {
		backgroundColor: 'var(--el-bg-color)',
		color: 'var(--el-text-color-primary)'
	},
	'.cm-content': {
		caretColor: 'var(--el-color-primary)'
	},
	'.cm-cursor, .cm-dropCursor': {
		borderLeftColor: 'var(--el-color-primary)'
	},
	'&.cm-focused .cm-selectionBackground, .cm-selectionBackground, .cm-content ::selection': {
		backgroundColor: 'var(--el-color-primary-light-7) !important'
	},
	'.cm-activeLine': {
		backgroundColor: 'var(--el-fill-color-light)'
	},
	'.cm-matchingBracket, .cm-nonmatchingBracket': {
		backgroundColor: 'var(--el-color-primary-light-8)',
		outline: '1px solid var(--el-color-primary-light-5)'
	},
	'.cm-gutters': {
		backgroundColor: 'var(--el-fill-color-lighter)',
		color: 'var(--el-text-color-placeholder)',
		border: 'none'
	},
	'.cm-activeLineGutter': {
		backgroundColor: 'var(--el-fill-color)'
	},
	'.cm-foldPlaceholder': {
		backgroundColor: 'var(--el-fill-color)',
		color: 'var(--el-text-color-secondary)'
	},
	'.cm-tooltip': {
		backgroundColor: 'var(--el-bg-color-overlay)',
		border: '1px solid var(--el-border-color-light)',
		borderRadius: 'var(--el-border-radius-base)'
	},
	'.cm-tooltip.cm-tooltip-autocomplete > ul > li[aria-selected]': {
		backgroundColor: 'var(--el-color-primary-light-9)',
		color: 'var(--el-color-primary)'
	},
	'.cm-lintRange-error': {
		backgroundImage: `url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='6' height='3'%3E%3Cpath d='M0 3 L3 0 L6 3' fill='none' stroke='%23f56c6c' stroke-width='1'/%3E%3C/svg%3E")`
	},
	'.cm-lintRange-warning': {
		backgroundImage: `url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='6' height='3'%3E%3Cpath d='M0 3 L3 0 L6 3' fill='none' stroke='%23e6a23c' stroke-width='1'/%3E%3C/svg%3E")`
	}
});
