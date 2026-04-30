# AGENTS.md

## 交流约定

- 与用户交流始终使用中文。
- 回答要简洁、明确，涉及代码修改时说明改了什么、如何验证。
- 不要回滚或覆盖用户未要求处理的改动；遇到工作区已有改动，先理解并顺着现状处理。

## 项目概览

Loom 是一个全栈 AI 内容生成平台：

- 前端：`frontend/`，Vue 3 + TypeScript + Vite + Pinia + Element Plus + `@cool-vue/crud`，基于 `cool-admin-vue 8.x`。
- 后端：`backend/`，FastAPI + SQLModel + Alembic + Celery + Redis，提供自动路由、EPS 元数据、权限和异步任务能力。
- 编排：根目录 `docker-compose.yml` 可启动 Redis、后端、Celery Worker、前端开发服务。

## 工作边界

- 修改前端规范、页面、组件、插件时，优先阅读 `frontend/.cursorrules` 和 `frontend/.cursor/rules/*.mdc`。
- 修改后端模块、控制器、Service、模型时，优先阅读 `backend/.cursor/rules/*.mdc`，再参考 `backend/app/modules` 现有模块结构和 `README.md` 的核心机制说明。
- 只改与当前任务相关的文件，避免顺手重构无关代码。
- 不要提交密钥、Token、真实账号或本地私有配置；`.env` 只作为本地运行配置。

## 前端约定

前端入口与结构：

- `frontend/src/cool`：框架核心、service、router、module bootstrap。
- `frontend/src/modules`：业务模块。
- `frontend/src/plugins`：项目插件。
- `frontend/packages`：本地源码包，例如 `@cool-vue/crud`、`@cool-vue/vite-plugin`。

重要别名：

- `"/@"` -> `frontend/src`
- `"/$"` -> `frontend/src/modules`
- `"/#"` -> `frontend/src/plugins`
- `"/~"` -> `frontend/packages`

开发规则：

- 文件、组件命名使用 kebab-case，例如 `student-info.vue`。
- 新增模块或插件前先读 `frontend/.cursor/rules/module.mdc`。
- CRUD、表格、表单、搜索、上传、权限、字典、菜单路由、菜单 SVG、Service/EPS 调用分别参考 `frontend/.cursor/rules` 下对应 `.mdc`。
- 业务接口优先使用 EPS：`service.{模块}.{控制器}.{方法}`；组件中优先通过 `useCool()` 获取 `service`。
- 常规后台页面放在 `src/modules/{module}/views/**`，通过后端菜单 `router` + `viewPath` 动态挂载。
- 菜单 SVG 图标放在模块 `static` 目录，菜单图标文件以 `icon-` 开头，菜单 `icon` 字段填写去掉 `.svg` 后的值。

前端常用命令在 `frontend/` 下运行：

```bash
npm run dev
npm run build
npm run type-check
npm run lint
npm run format
```

注意：`npm run lint` 和 `npm run format` 会改写文件，只在任务需要或用户允许时运行。

## 后端约定

后端入口与结构：

- `backend/main.py`：FastAPI 应用入口。
- `backend/app/core`：配置、数据库、安全、Redis、日志等核心能力。
- `backend/app/framework`：自动路由、EPS、响应封装、中间件、查询构建等框架层。
- `backend/app/modules/{module}`：业务模块，通常包含 `config.py`、`model/`、`service/`、`controller/`、`menu.json`。
- `backend/app/celery_app.py`：Celery 应用。

开发规则：

- 管理端 API 路由遵循 `/{scope}/{module}/{resource}/{action}`，例如 `/admin/base/sys/user/page`。
- 标准 CRUD 优先复用 `BaseAdminCrudService`，控制器优先使用 `CoolController` / `CoolControllerMeta`。
- 模型与 Service 内部字段遵循后端现有 snake_case 约定；API/EPS 面向前端时遵循现有字段映射机制。
- 菜单和权限优先通过模块 `menu.json`、EPS permission、后端初始化流程维护。
- Celery 任务放在模块任务目录或现有任务结构中，并确保 worker 可导入。

后端常用命令在 `backend/` 下运行：

```bash
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
uvicorn main:app --reload
celery -A app.celery_app worker --loglevel=info
python -m pytest
```

如使用 Docker，在根目录运行：

```bash
docker-compose up -d
```

## 验证建议

- 前端文档或 rules 修改：检查文件列表、关键词、frontmatter，不必运行构建。
- 前端代码修改：至少运行相关类型检查或构建；小范围样式/页面改动可启动 `npm run dev` 做人工验证。
- 后端代码修改：优先运行相关 `pytest`；涉及路由、EPS、权限、响应结构时重点跑 `backend/tests` 中的对齐测试。
- 跨前后端联动：确认后端 EPS 输出、前端 `build/cool/eps.d.ts` 或 service 使用方式是否需要同步。

## 代理操作习惯

- 搜索优先用 `rg` / `rg --files`。
- 手工编辑优先用补丁方式，避免生成大段无关格式化变更。
- 运行会改写文件的命令前先确认必要性。
- 不要删除 `data/`、`logs/`、`node_modules/`、`venv/`、构建产物或数据库文件，除非用户明确要求。
