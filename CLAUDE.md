# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Language

与用户交流始终使用中文。

## Commands

### 后端（在 `backend/` 下运行）

```bash
python -m venv venv && venv\Scripts\activate   # Windows 激活
pip install -r requirements.txt
uvicorn main:app --reload                         # 启动 API 服务
celery -A app.celery_app worker --loglevel=info   # 启动异步任务 Worker
python -m pytest                                  # 运行全部测试
python -m pytest tests/test_ai_module.py          # 运行单个测试文件
python -m pytest tests/test_ai_module.py -k "test_name"  # 按名称筛选
```

### 前端（在 `frontend/` 下运行）

```bash
npm install
npm run dev              # 开发服务器，端口 9090
npm run build            # 生产构建
npm run type-check       # TypeScript 类型检查 (vue-tsc)
npm run test:unit        # Vitest 单元测试
npm run test:e2e         # Playwright E2E 测试
npm run lint             # ESLint（会改写文件，仅在任务需要时运行）
npm run format           # Prettier（会改写文件，仅在任务需要时运行）
```

### Docker（在根目录运行）

```bash
docker-compose up -d     # 启动 Redis + 后端 + Celery Worker + 前端
```

## Architecture

Loom 是一个全栈 AI 内容生成平台，基于 Vue 3 + FastAPI + Celery。后端框架层参考 cool-admin-vue 的设计理念，在 Python 中实现了模块化自动路由、装饰器式 CRUD 控制器、EPS 元数据协议等。

### 后端：FastAPI + SQLModel + Celery

**入口**: `backend/main.py` — 应用生命周期（`lifespan`）中执行启动检查、建表、模块引导。

**核心层** (`app/core/`):
- `config.py` — `pydantic-settings` 配置管理，包含数据库、Redis、Celery、OpenAI、认证、限流等
- `database.py` — SQLModel + SQLAlchemy 2.0，支持 SQLite（开发）/ PostgreSQL（生产），自动建表和 schema 补列
- `security.py` — JWT 令牌、PBKDF2 密码哈希、令牌黑名单

**框架层** (`app/framework/`):
- `controller_meta.py` — `@CoolController` / `CoolControllerMeta` 装饰器，自动注册 CRUD 路由并导出 EPS
- `router/auto_router.py` — 按目录约定扫描 `controller/{scope}/` 自动注册路由
- `eps/` — EPS 元数据扫描与构建，驱动前端表单/表格/验证的自动生成
- `middleware/` — 认证、限流、日志、CORS、CSRF Origin、响应包装、操作日志
- `models/entity.py` — `BaseEntity` 基类，含 `id`、`created_at`、`updated_at`、`delete_time`
- `api/naming.py` — `resolve_alias` 字段别名映射（snake_case ↔ camelCase + 语义别名）
- `storage.py` — 本地/S3-compatible 文件存储
- `cache.py` — Redis 缓存（开发环境自动降级为进程内缓存）

**业务模块** (`app/modules/`): `base`（权限/认证）、`ai`（AI 模型）、`demo`、`dict`（字典）、`media`（媒体资源）、`notification`（通知）、`task`（异步任务）、`workflow`（工作流编排）。每个模块包含 `config.py`、`controller/`、`service/`、`model/`、可选 `menu.json`。

**模块加载** (`app/modules/loader.py`): 启动时扫描模块目录，注册路由、中间件、白名单和菜单。

**关键模式**:
- **路由**: `/{scope}/{module}/{resource}/{action}`，scope 包括 `admin`、`app`、`aiapi`、`open`
- **CRUD 控制器**: `@CoolController(CoolControllerMeta(...))` 声明式定义，`actions=("add","delete","update","page","info","list")` 自动生成接口。自定义接口使用 `@Post` / `@Get` 装饰器
- **Service**: 继承 `BaseAdminCrudService`，通过 `_before_add`、`_after_update` 等钩子植入业务逻辑
- **字段映射**: 内部 snake_case → API 响应通过 `resolve_alias` 转 camelCase。关键全局别名：`created_at→createTime`、`updated_at→updateTime`、`is_active→status`、`component→viewPath`、`path→router`
- **DTO**: Read 用 `from_attributes=True`，Request 用 `populate_by_name=True` + `alias_generator=resolve_alias`。Update DTO 继承 Create DTO 并加 `id`
- **软删除**: 模型含 `delete_time` 字段 + Controller meta 设 `soft_delete=True`
- **数据权限**: `DataScope` 在查询时自动注入权限过滤（全部/本人/本部门/本部门及下属/自定义）
- **统一响应**: `{ code: 1000, message, data }` 由 `ResponseEnvelopeMiddleware` 包装；分页为 `{ list, pagination: { page, size, total } }`；自定义分页返回 `PageResult`
- **Celery 队列**: `celery`、`default`、`ai.chat`、`ai.image`、`ai.embedding`、`ai.rerank`、`ai.audio`、`ai.video`

### 前端：Vue 3 + TypeScript + Vite（基于 cool-admin-vue 8.x）

**入口**: `frontend/src/main.ts` — 创建 Vue 应用，调用 `bootstrap`。

**核心** (`src/cool/`):
- `bootstrap/` — 初始化 Pinia → 注册路由 → 加载模块 → 初始化 EPS → 显示加载状态
- `bootstrap/module.ts` — 自动扫描 `src/{modules,plugins}/*/{config.ts,service/**,directives/**}` 按序加载
- `service/` — `BaseService` 提供 CRUD 方法，EPS 自动注入接口路径和类型
- `hooks/` — `useCool()` 获取 `service`、`router`、`mitt` 等

**业务模块** (`src/modules/`): `ai`、`base`、`dict`、`media`、`notification`、`task`、`workflow`。每个模块含 `config.ts`、`index.ts`、`views/`。

**路径别名**:
| 别名 | 路径 |
|------|------|
| `/@` | `src/` |
| `/$` | `src/modules/` |
| `/#` | `src/plugins/` |
| `/~` | `packages/` |

**EPS 类型**: `build/cool/eps.d.ts` 包含后端元数据生成的 TypeScript 类型定义。

**关键模式**:
- CRUD 页面使用 `@cool-vue/crud` 的 `useCrud`、`useTable`、`useUpsert`、`useSearch`
- 业务接口调用: `service.{模块}.{控制器}.{方法}`
- 文件/组件命名使用 kebab-case
- 菜单路由由后端 `/admin/base/menu/currentTree` 动态驱动
- 组件缓存: `defineOptions({ name: "xxx" })`
- 菜单 SVG 图标放在模块 `static` 目录，以 `icon-` 开头

## Development Rules

### 后端新增模块

1. 创建 `app/modules/{module}/` 目录，包含 `config.py`（声明 `MODULE_CONFIG`）、`model/`、`service/`、`controller/`，按需添加 `menu.json`
2. Controller 文件按 scope 分目录：`controller/{scope}/xxx.py`，文件末尾导出 `router = XxxController.router`
3. Service 继承 `BaseAdminCrudService`，返回数据前经 `_finalize_data()` 转换
4. 查询字段映射使用 `QueryFieldConfig(column, request_param)`
5. 初始化脚本保持幂等，白名单使用完整后端接口路径

详细规范参考 `backend/.cursor/rules/` 下的 `.mdc` 文件：`module.mdc`、`controller.mdc`、`service-crud.mdc`、`model-schema.mdc`、`eps-response.mdc`、`task-celery.mdc`、`testing.mdc`

### 前端新增模块

1. 创建 `src/modules/{module}/`，包含 `config.ts`、`index.ts`、`views/`
2. 阅读 `frontend/.cursor/rules/module.mdc` 了解模块注册规范

详细规范参考 `frontend/.cursor/rules/` 下的 `.mdc` 文件：`crud.mdc`、`form.mdc`、`table.mdc`、`upsert.mdc`、`search.mdc`、`service-call.mdc`、`menu-route-viewpath.mdc`、`permission.mdc`

### 验证

- 后端代码修改：运行相关 `pytest`；涉及路由/EPS/权限/响应结构时跑 `tests/test_framework_alignment.py`
- 前端代码修改：运行 `npm run type-check` 或 `npm run build`
- 跨前后端联动：确认后端 EPS 输出与前端 `build/cool/eps.d.ts` 同步

### 通用约定

- 只改与当前任务相关的文件，不顺手重构无关代码
- 运行 `lint` 或 `format` 前确认必要性（它们会改写文件）
- 不要删除 `data/`、`logs/`、`node_modules/`、`venv/`、构建产物或数据库文件
- 搜索和参考现有模块实现，保持一致的模式和命名

### 参考文档

- `AGENTS.md` — 代理工作边界和约定
- `docs/` — 框架说明、自动路由、EPS 规范、字段映射、Controller/Service/Model 使用规范等
- `frontend/.cursorrules` — 前端目录结构和别名
- `frontend/.cursor/rules/` — 前端开发规范（CRUD、模块、表单、表格、权限等 `.mdc` 文件）
- `backend/.cursor/rules/` — 后端开发规范（模块、控制器、Service、模型、测试、EPS 等 `.mdc` 文件）
