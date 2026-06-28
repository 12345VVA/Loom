# Loom Frontend

Loom 管理端前端，基于 Vue 3、TypeScript、Vite、Element Plus 与 Pinia 构建。

## 开发

```shell
npm install
npm run dev
```

默认开发服务会通过 `/dev` 代理到本地后端 `http://127.0.0.1:8000`。

## 校验

### 类型检查

```shell
npm run type-check
```

### ESLint（代码规范检查）

```shell
npm run lint:check     # 只检查，不修改文件（CI 用）
npm run lint           # 检查并自动修复（eslint . --fix）
```

### Prettier（代码格式化）

```shell
npm run format:check   # 只检查哪些文件不符合格式，不修改
npm run format         # 按规则格式化 src/（prettier --write）
```

### 生产构建

```shell
npm run build
```

## 编辑器集成（VSCode）

项目根 `.vscode/` 已配置「保存时自动格式化」，首次打开会提示安装推荐扩展（Prettier、ESLint、Volar）。

- 保存前端文件（vue / ts / js / json）时，Prettier 自动格式化；
- 保存时 ESLint 自动修复可修复规则（如组件名 kebab-case、`prefer-const` 等）；
- 职责分工：Prettier 负责格式，ESLint 负责非格式规则（已在 `eslint.config.js` 通过 `skip-formatting` 关闭 ESLint 的格式规则）。

> 命令均在 `frontend/` 目录下执行。批量检查可在提交前运行 `npm run lint:check` 与 `npm run format:check`。
