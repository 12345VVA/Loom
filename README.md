# Loom - AI 内容生成平台

> Loom 一个很酷的全栈 AI 内容生成平台。基于 Vue 3 + FastAPI + Celery 深度定制，提供模块化后台管理、自动路由、权限、EPS 元数据和 AI 异步任务能力。

## 特点

- **模块化架构**: 模块之间高度解耦，支持独立的中间件、路由、数据初始化及权限白名单。
- **极速 CRUD**: 仅需定义模型与装饰器，一行代码即可实现全量管理后端接口。
- **EPS 指令集**: 自动扫描并导出后端模型元数据，驱动前端表单、验证与表格的自动生成。
- **企业级数据权限**: 内置 `DataScope` 机制，支持“本人、本部门、本部门及下属”等多种粒度的数据自动过滤。
- **AI 异步引擎**: 深度集成 Celery + Redis，完美支持大规模、高并发的长耗时 AI 生成任务。
- **动态路由与权限**: 基于 JWT 与服务端二级缓存，支持动态菜单同步与精确到 Action 的权限校验。

## 技术栈

### 前端
- Vue 3 + TypeScript
- Pinia (状态管理)
- Vue Router
- Axios
- Vite

### 后端
- FastAPI (异步 API 框架)
- SQLModel (ORM)
- Alembic (数据库迁移)
- Celery (异步任务)
- Redis (消息队列/缓存)
- OpenAI SDK / Ollama (AI 模型)

### 基础设施
- Docker & Docker Compose

## 项目结构

```
Loom/
├── frontend/           # Vue 3 前端
│   ├── src/
│   │   ├── cool/      # 框架核心、service、router、module bootstrap
│   │   ├── modules/   # 业务模块页面、store、静态资源
│   │   ├── plugins/   # 项目插件
│   │   ├── config/    # 环境与代理配置
│   │   └── main.ts    # 前端入口
│   ├── packages/      # 本地源码包，如 @cool-vue/crud、vite-plugin
│   ├── tests/         # Vitest 单元测试与 Playwright E2E
│   └── Dockerfile
├── backend/           # FastAPI 后端
│   ├── app/
│   │   ├── core/     # 核心配置
│   │   ├── framework/ # 自动路由与中间件框架
│   │   └── modules/   # 模块化业务代码
│   ├── tests/        # pytest 自动化测试
│   ├── alembic/      # 数据库迁移骨架
│   └── Dockerfile
├── docs/              # 当前有效项目文档
├── scripts/           # 本地验证脚本
├── docker-compose.yml # Docker 编排配置
└── README.md
```

## 快速开始

### 使用 Docker Compose (推荐)

1. 复制环境变量文件:
```bash
cp .env.example .env
```

2. 编辑 `.env` 文件，填入你的 OpenAI API Key 或配置本地 Ollama

3. 启动所有服务:
```bash
docker-compose up -d
```

4. 访问应用:
- 前端: http://localhost:5173
- 后端 API: http://localhost:8000
- API 文档: http://localhost:8000/docs

### 本地开发

#### 后端开发

1. 创建 Python 虚拟环境并安装依赖:
```bash
cd backend
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate
pip install -r requirements.txt
```

2. 配置环境变量:
```bash
cp .env.example .env
# 编辑 .env 文件配置你的 API Key
```

3. 启动 FastAPI 服务:
```bash
uvicorn main:app --reload
```

4. 启动 Celery Worker (新终端):
```bash
cd backend
celery -A app.celery_app worker --loglevel=info
```

#### 前端开发

1. 安装依赖:
```bash
cd frontend
npm install
```

2. 启动开发服务器:
```bash
npm run dev
```

## 核心机制

### 自动建表 (Auto Table Creation)

项目采用 **SQLModel (SQLAlchemy)** 实现全自动数据库建模：
- **启动即建表**: 应用在每次通过 `uvicorn` 启动时，会在 `main.py` 的 `lifespan` 生命周期中调用 `init_db()`。
- **元数据同步**: 自动扫描所有已加载模块中的 `model` 定义，并创建对应的数据表。
- **兼容性补丁**: 针对 SQLite 环境，框架在 `app/core/database.py` 中实现了 schema 自动修补机制，能够自动为旧表补充缺失的字段（如 `delete_time` 等），降低开发阶段的迁移成本。

### 自动路由与 EPS (Auto Routing & EPS)

项目基于装饰器元数据实现高度自动化的路由聚合与元数据导出：
- **CoolController**: 通过在该控制器类上使用 `@CoolController` 装饰器，自动将类方法注册为 API 接口。
- **URL 结构**: 遵循 `/{scope}/{module}/{resource}/{action}` 的标准命名规范，例如：`/admin/base/sys/user/page`。
- **EPS (Entity-Permission-System)**: 框架会自动扫描 Pydantic/SQLModel 模型定义，提取字段类型、枚举值、验证规则及描述，导出为前端识别的元数据。这使得前端可以根据后端定义自动渲染表单、表格和验证逻辑。

### 数据权限 (Data Scope)

内置企业级的数据权限隔离机制：
- **声明式控制**: 在 `Role` 模型中定义 `data_scope`（全部、本人、本部门、本部门及下属、自定义）。
- **无感注入**: `QueryBuilder` 会在执行查询前自动注入当前用户的权限过滤 SQL（如 `WHERE department_id IN (...)`），无需在业务代码中手动处理隔离逻辑。
- **字段约定**: 默认识别模型中的 `user_id` 和 `department_id` 字段进行隔离。

### CRUD 增强与生命周期钩子 (CRUD & Hooks)

通过 `BaseAdminCrudService` 提供标准化的业务抽象：
- **通用能力**: 自动实现分页、列表、详情、增删改等标准接口。
- **生命周期钩子**: 子类可以通过覆盖 `_before_add`, `_after_add`, `_before_update` 等方法，在不破坏通用流程的情况下植入业务特有的逻辑（如密码加密、关联表同步、缓存清理等）。
- **字段转换**: 自动处理 `snake_case` (DB) 与 `camelCase` (API) 的字段映射。
  约定为模型与 Service 内部使用 `snake_case`，响应与 EPS 中的 `prop/propertyName` 输出前端字段名，`source` 保留后端源字段名。

### 菜单初始化 (Menu Initialization)

系统支持通过声明式配置文件初始化系统菜单与角色权限：
- **menu.json**: 每个业务模块均可在其目录下维护 `menu.json`，定义该模块所需的菜单树、路由组件路径及权限标识。
- **自动同步**: 启动时 `bootstrap_modules` 会扫描所有模块的菜单配置，并调用 `AuthService.bootstrap_defaults()` 将其持久化至 `sys_menu` 表。
- **角色分配**: 支持在 JSON 中配置 `role_codes`，系统会自动建立菜单与对应角色（如 `admin`）的关联关系。
- **使用示例**: 在模块根目录创建 `menu.json`：
  ```json
  [
    {
      "name": "任务管理",
      "code": "task_manage",
      "type": "menu",
      "path": "/task",
      "component": "/task/index",
      "icon": "icon-task",
      "role_codes": ["admin"],
      "children": [
        { "name": "任务列表", "code": "task_list", "type": "menu", "path": "/task/list", "permission": "task:task:page" }
      ]
    }
  ]
  ```

### 模块化与中间件隔离 (Modularity)

为了支持高内聚、低耦合的模块化开发，框架提供了以下特性：
- **前缀作用域中间件**: 支持通过 `PrefixScopedMiddleware` 将中间件绑定到特定的模块或 URL 前缀，使得认证、日志等逻辑可以按需差异化配置，互不干扰。
- **模块自治**: 模块配置（`config.py`）可以声明自己的白名单、全局或局部中间件、数据初始化脚本等。

### 软删除支持 (Soft Delete)

框架对业务建模中的物理删除与软删除提供了透明支持：
- **自动识别**: 只要模型中定义了 `delete_time` 字段，`QueryBuilder` 会在所有的查询操作中自动过滤掉已删除的记录。
- **统一 API**: 在 Service 层调用 `delete` 时，系统会根据元数据配置自动选择执行 `UPDATE`（置空 `delete_time`）还是 `DELETE` 操作。

## 框架完善度与后续建议

当前框架主干机制已基本完善，并已有后端 pytest、前端单元测试、类型检查和构建命令覆盖关键路径：

- **已完善**: 模块加载、自动路由、`CoolController` CRUD、EPS 输出、管理端鉴权、RBAC、DataScope、统一响应、字段映射、Redis/内存缓存降级、上传校验、S3-compatible 存储、健康检查、`/metrics`、限流、CSRF Origin 检查、密码强度/哈希升级、验证码防重放、Token 吊销、会话并发控制、操作/登录/安全日志、启动配置校验、统一事务 helper、缓存命名空间、导入导出 schema 校验、任务保守调度和 Alembic baseline。
- **后续生产化建议**: 接入集中日志与告警平台、为业务模块声明导入导出字段白名单和权限点、为跨进程事件补可靠消费确认、将更多多表业务逐步迁移到统一事务 helper。
- **当前边界**: Python 后端通过显式元数据对象承载控制器声明，不依赖 Midway/TypeScript 反射；EPS 已覆盖当前前端需要的字段与接口元数据，但不是 TypeScript 原生反射生成；SQLite 自动补列主要服务开发阶段，生产环境应以 Alembic 迁移为准。



## API 规范与兼容性

本项目后端 API 面向 Loom 管理端前端设计，统一输出 `{ code, message, data }` 响应结构，并通过 EPS 元数据驱动前端 service、表格和表单。

### 命名规范
路由遵循 `/{scope}/{module}/{resource}/{action}` 结构：
- **scope**: 访问域隔离。`admin` 为管理后台，`app` 为移动端/用户端，`aiapi` 为 AI 开放接口。
- **module**: 业务模块名称。如 `base` (权限), `task` (任务), `dict` (字典)。
- **resource**: 资源标识。如 `sys/user`, `sys/role`。
- **action**: 动作指令。对应 `BaseAdminCrudService` 提供的标准操作。

### 标准 CRUD 动作
所有基于 `BaseController` 开发的资源默认具备以下动作：
| 动作 | 方法 | 描述 |
|------|------|------|
| `add` | POST | 新增记录 |
| `delete` | POST | 批量删除记录 |
| `update` | POST | 更新记录 |
| `info` | GET | 获取单条详情 |
| `list` | GET / POST | 获取全量列表，POST 为 Loom 主协议，GET 为兼容入口 |
| `page` | GET / POST | 获取分页列表 (支持高级搜索)，POST 为 Loom 主协议，GET 为兼容入口 |

### 完整文档
项目启动后，请访问以下路径查看实时互动的完整 API 文档：
- **API 文档**: [http://localhost:8000/docs](http://localhost:8000/docs)
- **Redoc**: [http://localhost:8000/redoc](http://localhost:8000/redoc)
- **项目说明文档索引**: [docs/README.md](./docs/README.md)


## 环境变量

### 后端 (.env)
- `DATABASE_URL`: 数据库连接字符串
- `REDIS_URL`: Redis 连接字符串
- `JWT_SECRET_KEY`: JWT 密钥，建议至少 32 字节
- `OPENAI_API_KEY`: OpenAI API 密钥
- `OPENAI_BASE_URL`: OpenAI API 基础 URL
- `CORS_ORIGINS` / `CORS_ALLOW_METHODS` / `CORS_ALLOW_HEADERS`: CORS 来源、方法与头白名单
- `ADMIN_CSRF_ORIGIN_CHECK_ENABLED`: 是否启用管理端变更请求 Origin/Referer 校验
- `RESPONSE_ENVELOPE_MAX_BYTES`: 统一响应包装最大 JSON 体积，超出后跳过包装
- `MODULE_LOAD_STRICT`: 模块加载失败时是否直接中断启动
- `PASSWORD_PBKDF2_ITERATIONS`: PBKDF2 密码哈希迭代次数，登录成功后自动升级旧哈希
- `ADMIN_SESSION_MAX_CONCURRENT`: 管理端同一用户最大并发会话数，`0` 表示不限制
- `STORAGE_PROVIDER` 与 `S3_*`: 本地或 S3-compatible 文件存储配置
- `METRICS_ENABLED`: 是否记录并开放 `/metrics` 文本指标
- `DB_POOL_*`: 非 SQLite 数据库连接池参数
- `API_VERSION_PREFIX_ENABLED`: 是否额外挂载 `/api/v1` 兼容前缀

### 前端 (.env)
- `VITE_API_BASE_URL`: 后端 API 基础 URL

## 说明

- 管理端接口统一走 `/admin/*`
- `base` 和 `task` 模块都已切到动作式管理接口风格
- 前端业务页不再由静态路由表维护，而是根据 `/admin/base/menu/currentTree` 动态注册
- `/tasks/:id` 作为任务详情补充路由，依赖 `/tasks` 菜单权限
- 自动路由说明见 [docs/模块自动路由与管理端鉴权说明.md](./docs/模块自动路由与管理端鉴权说明.md)
- 本地若未启动 Redis，开发模式会自动回退到进程内缓存；生产环境应使用真实 Redis
- `/health` 返回数据库、Redis、Celery 配置检查；`/metrics` 默认关闭，可通过 `METRICS_ENABLED` 启用

## 开源协议

本项目采用 [MIT License](./LICENSE) 协议开源。
