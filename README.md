# Loom - AI 内容生成平台

基于 Vue 3 + FastAPI + Celery 的全栈 AI 内容生成平台。

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
│   │   ├── api/       # API 调用
│   │   ├── components/# 组件
│   │   ├── router/    # 路由
│   │   ├── stores/    # Pinia 状态管理
│   │   ├── types/     # TypeScript 类型
│   │   └── views/     # 页面视图
│   └── Dockerfile.dev
├── backend/           # FastAPI 后端
│   ├── app/
│   │   ├── core/     # 核心配置
│   │   ├── framework/ # 自动路由与中间件框架
│   │   └── modules/   # 模块化业务代码
│   ├── venv/         # Python 虚拟环境
│   └── Dockerfile
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

## 功能特性

- **登录与权限**: 管理端采用 `JWT + 服务端缓存态 + URL 权限匹配`
- **动态菜单与动态路由**: 登录后按后端菜单树动态生成前端导航与页面入口
- **基础数据权限**: 已按角色 `data_scope` 在用户列表与任务列表层面收敛查询范围
- **异步 AI 生成**: 使用 Celery 处理耗时的 AI 生成任务
- **实时进度跟踪**: 任务状态实时更新
- **任务管理**: 创建、查看、取消 AI 生成任务
- **多种 AI 模型支持**: 支持 OpenAI API 和本地 Ollama

## API 端点

| 方法 | 端点 | 描述 |
|------|------|------|
| POST | `/admin/base/open/login` | 管理端登录 |
| POST | `/admin/base/open/refresh` | 刷新访问令牌 |
| POST | `/admin/base/open/logout` | 退出登录 |
| GET | `/admin/base/user/me` | 获取当前用户 |
| GET | `/admin/base/user/list` | 获取用户列表 |
| GET | `/admin/base/user/page` | 获取用户分页 |
| POST | `/admin/base/user/add` | 创建用户 |
| POST | `/admin/base/user/update` | 更新用户 |
| POST | `/admin/base/user/delete` | 删除用户 |
| POST | `/admin/base/user/assignRoles` | 分配用户角色 |
| GET | `/admin/base/role/list` | 获取角色列表 |
| GET | `/admin/base/role/page` | 获取角色分页 |
| POST | `/admin/base/role/add` | 创建角色 |
| POST | `/admin/base/role/update` | 更新角色 |
| POST | `/admin/base/role/delete` | 删除角色 |
| POST | `/admin/base/role/assignMenus` | 分配角色菜单 |
| GET | `/admin/base/menu/list` | 获取菜单列表 |
| GET | `/admin/base/menu/page` | 获取菜单分页 |
| POST | `/admin/base/menu/add` | 创建菜单 |
| POST | `/admin/base/menu/update` | 更新菜单 |
| POST | `/admin/base/menu/delete` | 删除菜单 |
| GET | `/admin/base/menu/tree` | 获取菜单树 |
| GET | `/admin/base/menu/currentTree` | 获取当前用户动态菜单树 |
| GET | `/admin/base/health/ping` | 管理端健康检查 |
| GET | `/app/base/health/ping` | App 作用域健康检查 |
| GET | `/aiapi/base/health/ping` | AI API 作用域健康检查 |
| POST | `/admin/task/task/add` | 创建新任务 |
| GET | `/admin/task/task/list` | 获取任务列表 |
| GET | `/admin/task/task/page` | 获取任务分页 |
| GET | `/admin/task/task/info?id=...` | 获取任务详情 |
| POST | `/admin/task/task/update` | 更新任务 |
| POST | `/admin/task/task/delete` | 删除任务 |
| POST | `/admin/task/task/cancel` | 取消任务 |

## 环境变量

### 后端 (.env)
- `DATABASE_URL`: 数据库连接字符串
- `REDIS_URL`: Redis 连接字符串
- `JWT_SECRET_KEY`: JWT 密钥，建议至少 32 字节
- `OPENAI_API_KEY`: OpenAI API 密钥
- `OPENAI_BASE_URL`: OpenAI API 基础 URL

### 前端 (.env)
- `VITE_API_BASE_URL`: 后端 API 基础 URL

## 说明

- 管理端接口统一走 `/admin/*`
- `base` 和 `task` 模块都已切到动作式管理接口风格
- 前端业务页不再由静态路由表维护，而是根据 `/admin/base/menu/currentTree` 动态注册
- `/tasks/:id` 作为任务详情补充路由，依赖 `/tasks` 菜单权限
- 自动路由说明见 [docs/module-routing-guide.md](./docs/module-routing-guide.md)
- 本地若未启动 Redis，开发模式会自动回退到进程内缓存；生产环境应使用真实 Redis
