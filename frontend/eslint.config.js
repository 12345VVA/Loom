import pluginVue from 'eslint-plugin-vue';
import vueTsEslintConfig from '@vue/eslint-config-typescript';
import skipFormatting from '@vue/eslint-config-prettier/skip-formatting';

export default [
	{
		name: 'app/files-to-lint',
		files: ['**/*.{ts,mts,tsx,vue}'],
	},

	{
		name: 'app/files-to-ignore',
		ignores: [
			'**/dist/**',
			'**/dist-ssr/**',
			'**/coverage/**',
			'**/packages/**',
			'**/build/**',
		],
	},

	...pluginVue.configs['flat/recommended'],
	...vueTsEslintConfig(),
	skipFormatting,

	{
		languageOptions: {
			parserOptions: {
				ecmaVersion: 2020,
				ecmaFeatures: {
					jsx: true,
				},
			},
		},
		rules: {
			'@typescript-eslint/ban-ts-ignore': 'off',
			'@typescript-eslint/explicit-function-return-type': 'off',
			'@typescript-eslint/no-explicit-any': 'warn',
			'@typescript-eslint/no-var-requires': 'off',
			'@typescript-eslint/no-empty-function': 'off',
			'@typescript-eslint/no-use-before-define': 'off',
			'@typescript-eslint/ban-ts-comment': 'off',
			'@typescript-eslint/ban-types': 'off',
			'@typescript-eslint/no-non-null-assertion': 'off',
			'@typescript-eslint/explicit-module-boundary-types': 'off',
			'@typescript-eslint/no-namespace': 'off',
			'@typescript-eslint/no-unused-vars': 'warn',
			'@typescript-eslint/no-empty-object-type': 'off',
			'space-before-function-paren': 'off',
			'no-unused-vars': 'off', // TS 项目由 @typescript-eslint/no-unused-vars 接管，原生规则在 TS 语法上会崩溃
			'no-use-before-define': 'off',
			'no-self-assign': 'off',
			'vue/no-mutating-props': 'off',
			'vue/no-template-shadow': 'off',
			'vue/no-v-html': 'warn',
			'vue/component-name-in-template-casing': ['error', 'kebab-case'],
			'vue/component-definition-name-casing': ['error', 'kebab-case'],
			'vue/attributes-order': 'off',
			'vue/one-component-per-file': 'off',
			'vue/html-closing-bracket-newline': 'off',
			'vue/max-attributes-per-line': 'off',
			'vue/multiline-html-element-content-newline': 'off',
			'vue/multi-word-component-names': 'off',
			'vue/singleline-html-element-content-newline': 'off',
			'vue/attribute-hyphenation': 'off',
			'vue/html-self-closing': 'off',
			'vue/require-default-prop': 'off',
			'vue/v-on-event-hyphenation': 'off',
			'vue/block-lang': 'off',
		},
	},
];
