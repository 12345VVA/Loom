# Loom — AI 内容生成 + Agent 工作流平台

> Loom 是一个面向企业的全栈 AI 内容生成与 Agent 工作流平台。它把多厂商 AI 模型统一运行时、可视化工作流编排、工作流评测与回归、企业级治理与计费整合到同一套后端，让业务方在画布上拼装 AI 流程，并通过统一的 Profile 抽象消费 12 家厂商的能力，无需关心底层差异。

## 核心业务能力

Loom 围绕以下九大业务域组织：

- **AI 模型管理**：三层配置（Provider/Model/Profile）+ 12 家厂商适配器 + 6 种 AI 能力，密钥集中加密，Profile 抽象对业务屏蔽厂商差异。
- **可视化工作流编排**：基于 LangGraph 的编译型引擎 + Vue Flow 画布 + 15 种已注册节点执行器 + 人工交互挂起/恢复 + Redis pub/sub 实时推送。
- **工作流评测与回归**：测试集 / 测试用例 / 评估运行 / 回归对比四类对象，每用例跑真实 WorkflowInstance 全链路，三类评估器（rule_match / llm_judge / composite）。
- **人工标注与 κ 校准**：独立 workflow_annotation 模块支撑标注队列与 judge 一致性校准，让 LLM judge 从「能用」走向「可信」。
- **企业级 AI 治理与安全**：治理三维（范围 × 周期 × 模式）× 四维限流（请求/并发/Token/成本）+ 提示注入检测 + PII 脱敏 + 会话并发控制。
- **可观测与计费**：调用日志统一以微美元计量成本，用量看板 + 操作/登录/安全三类审计日志 + `/health` + `/metrics`。
- **通用定时任务调度**：task 模块作为通用系统定时调度器，cron / 间隔触发 + Celery Beat 扫描 + 反射执行，与业务解耦。
- **通知系统**：站内 / 业务 / 任务通知 + 模板化发送。
- **媒体 / 字典 / 权限**：本地与 S3 兼容文件存储、字典枚举管理、基于 JWT + 动态菜单的细粒度权限。

## 技术栈

### 前端
- Vue 3 + TypeScript + Vite（开发服务器端口 9090）
- Pinia + Vue Router + Axios
- Element Plus + `@cool-vue/crud`（基于 cool-admin-vue 8.x）
- **Vue Flow**（`@vue-flow/core`）可视化工作流编辑器

### 后端
- FastAPI（异步 API 框架）
- SQLModel + SQLAlchemy 2.0（ORM）+ Alembic（数据库迁移）
- **Celery**（异步任务）+ **Celery Beat**（定时调度）
- **Redis**（消息队列 / 缓存 / 工作流事件总线 pub/sub）
- **LangGraph**（工作流编译与执行引擎）

### AI 与编排
- OpenAI SDK / Anthropic SDK / Google GenAI SDK / Volcengine SDK 等
- LangGraph StateGraph + Checkpoint 持久化
- 自研 SafeEvaluator（AST 白名单安全求值）

### 基础设施
- Docker & Docker Compose
- 本地 / S3-compatible 文件存储
- 进程内缓存（开发降级）/ Redis 缓存（生产）

## 工作流编排引擎

Loom 的工作流引擎以 **LangGraph** 为执行内核，前端画布拓扑先经拓扑校验再编译为 StateGraph，运行期是编译后的图，比解释执行更可靠。完整设计见 [AI 与工作流系统架构说明](./docs/AI与工作流系统架构说明.md)。

### LangGraph 编译链路

`compiler.py` 把前端画布拓扑编译为 LangGraph StateGraph：

```
validate_graph(拓扑校验) → 递归编译子图(loop/batch) → 主图 add_node → add_edge → 条件分流 add_conditional_edges
```

`validate_graph` 前置校验：缺 START 节点、悬空/重复边、子图路由、孤立节点、静态环路检测（DFS）、模型节点配置完整性。条件分流节点（condition / intent_classifier / switch）的出边由运行时路由决定，不参与静态环检测；循环 / 批处理节点在编译期提取为独立子图。

### 15 种已注册节点执行器

> 节点系统通过 `NodeExecutorRegistry` 注册（`(state, config) -> dict`），可扩展。下表为当前已注册清单，含 `tool`（旧版兼容执行器）。

| 类别 | 节点 | 说明 |
|------|------|------|
| 基础 | `start` / `end` | 流程起止 |
| AI | `llm` / `image_generator` / `intent_classifier` | 调用 AI 运行时（chat / image / 意图分类） |
| 逻辑 | `condition`（T/F 双端口）/ `switch`（动态端口）/ `loop_controller` / `batch_processor` | 条件分流、循环、批处理 |
| 系统 | `tool_executor` / `human_input` / `variable_assignment` / `variable_transform` / `tool`（旧） | 工具调用、人工交互、变量赋值/变换 |
| 容器 | `loop_body_group` | 循环体容器 |

代表性执行器行为：
- **LLM 节点**：分层 JSON 输出（Tier1 `json_schema` / Tier2 `json_object` / Tier3 纯文本）。
- **循环控制器**：状态链式循环（上一次输出作为下次输入）。
- **批处理**：`asyncio.gather + Semaphore` 控制并发（限 1–20）。
- **人工交互**：用 LangGraph 原生 `interrupt` 挂起，靠 checkpoint 恢复，恢复时通过 `Command(resume=...)` 注入外部输入。

### 可视化编辑器

前端基于 `@vue-flow/core` 实现可视化编辑器，配套 15 种节点的统一基础节点与配置面板，并提供三级变量体系（全局上游 / 循环上下文 / 局部输入）与变量选择器。调试能力包含试运行（递增延迟轮询）、单节点测试（令牌防并发）、实时日志抽屉。

### Checkpoint 持久化

`checkpointer.py` 支持三种后端，由 `WORKFLOW_CHECKPOINT_BACKEND` 配置：

| 后端 | 适用场景 |
|------|----------|
| `memory` | 默认开发模式，进程内 |
| `sqlite` | 单机持久化（audit S3 后默认） |
| `postgres` | 生产环境多 worker 共享 |

Checkpoint 是人工交互挂起/恢复的基础——`human_input` 节点 `interrupt` 后状态落入持久化后端，恢复时从 checkpoint 还原继续执行。

### 事件总线与 SSE

`event_bus.py` 用 Redis pub/sub 跨进程推送节点执行事件；实例控制器 `/admin/workflow/instance/stream` 以 SSE 实时下发到前端，使前端试运行 / 实例监控能看到节点级实时进度。

### 变量与表达式系统

- **模板渲染**：`render_template` 支持 `{var}` / `{var.field}` / `{var.list.0}` 语法。
- **安全求值**：自研 `SafeEvaluator`（AST 白名单，防条件表达式代码注入）。
- **输入/输出映射**：节点可声明 `inputs` schema（变量名 + 类型 + 上游引用 source）实现严格数据流；未声明则透传全局变量。

### 健壮性设计

- **原子 CAS 状态机**：`resume` / `cancel` 用 `UPDATE ... WHERE status=?` 消除 TOCTOU 竞态。
- **防重放**：启动 2 秒去重、单节点测试 Redis 去重（429）。
- **稳定 Handle ID**：前端 `genId()` + 后端 `case_${stableId}`，解决删除中间分支导致连线错位。
- **数据权限**：`assert_workflow_owner` 限定非超管只能操作本人工作流。

### 工作流消费 AI 运行时的关键链路

工作流不直接接触厂商 API，而是通过 `profile_code` 引用 AI 模块统一运行时，复用其治理 / 安全 / 日志 / 计费能力：

```
前端 LLM 节点配置 (modelProfileCode) 
    → 保存到 graph_json 
    → 后端 compiler 编译 
    → execute_llm_node 
    → run_ai_chat() 
    → AiModelRuntimeService.chat() 
    → 经过 治理检查 → 适配器 → 重试 → 成本计算 → 日志 
    → 返回 content 
    → 写入 output_variable 
    → 下游节点引用
```

`run_ai_chat` 以 `skip_masking=True` 跳过脱敏（工作流内部数据），并做空响应拦截防御。

## 工作流评测系统

Loom 内置一套面向工作流的回归评测 harness（不仅仅是单 LLM 评测），围绕「同一测试集 × 不同图版本，跑真实实例 + 规则/LLM 打分 + 按 case_key 对齐 diff」组织。详细对标分析见 [评测系统对标分析-2026-06-26](./docs/评测系统对标分析-2026-06-26.md)。

### 四类业务对象

| 对象 | 实体 | 职责 |
|------|------|------|
| 测试集 | `WorkflowTestSet` | 一组测试用例集合 |
| 测试用例 | `WorkflowTestCase` | 单条 input / expected / case_key |
| 评估运行 | `WorkflowEvalRun` | 一次完整跑测，含图快照与统计结果 |
| 回归对比 | 多版本 `WorkflowEvalRun` 对齐 | 按 case_key 比对 pass_rate / avg_score / cost 趋势 |

### 三类评估器

| 评估器 | 说明 |
|--------|------|
| `rule_match` | 规则匹配，支持 exact / contains / regex / numeric 四种模式 |
| `llm_judge` | 单次 pointwise 0-1 打分 |
| `composite` | 多评估器加权组合 |

评估器通过 `EvaluatorRegistry` 装饰器注册，扩展点已留好。

### 设计亮点

- **graph_json_snapshot 图快照**：每次评估运行记录当时的图拓扑快照，历史回归可比，不依赖 definition 当前版本。
- **真实 WorkflowInstance 全链路执行**：每个用例建真实实例跑完整编译 → 执行 → SSE 链路，能测到节点 / governance / 事件总线真实行为，不是 mock 执行。
- **contextvar 精确 token / cost 关联**：按工作流实例精确聚合 Token 与成本，比同类系统的近似估算更准。

### 健壮性

- **CAS 状态机**：评估运行状态变更走原子 UPDATE，消除竞态。
- **sweep 超时巡检**：后台巡检挂死实例并兜底收尾，达生产级健壮性。
- **失败兜底**：单用例失败不阻断整批，最终汇总失败明细。

### 人工标注与 κ 校准

独立 `workflow_annotation` 模块提供标注队列与多标注者一致性校准（Cohen's κ / Fleiss' κ），用 gold set 测 LLM judge 与人工标注的一致性，把 κ 作为 judge 可信度指标显示出来。这是让 LLM judge 从「能用」走向「可信」的关键闭环。

## AI 模型统一运行时

AI 模块以 `AiModelRuntimeService` 为核心，对外暴露统一的调用入口，对内通过工厂模式适配 12 家厂商。详细设计见 [AI 与工作流系统架构说明](./docs/AI与工作流系统架构说明.md)。

### 三层配置架构

| 层级 | 实体 | 职责 |
|------|------|------|
| Provider 厂商 | `AiProvider` | 接入凭证 + base_url（`adapter` / `api_key_cipher` / `api_key_mask` / `extra_config`） |
| Model 模型 | `AiModel` | 模型能力与定价（`model_type` / `context_window` / `pricing_config`） |
| Profile 调用配置 | `AiModelProfile` | 业务侧调用参数（`code` / `temperature` / `retry_count` / `fallback_profile_id` / `is_default`） |

**Profile 是业务唯一入口**：业务侧只认 `profile_code`，厂商 / 模型变更对调用方透明；支持配置级兜底（`fallback_profile_id`），主配置失败可自动降级。厂商密钥集中加密存储（`api_key_cipher`），前端只回显脱敏串 `api_key_mask`。

### 12 家厂商适配器

`openai-compatible`、`ollama`、`gemini`、`claude`、`deepseek`、`volcengine-ark`（火山方舟）、`bailian`（阿里百炼）、`hunyuan`（腾讯混元）、`qianfan`（百度千帆）、`zhipu`（智谱）、`minimax`、`mimo`（小米）

适配器基类统一了 `chat / stream_chat / embedding / image / audio / video / rerank / test / list_models` 接口。代表性特殊处理：Claude 的 `x-api-key` 认证与 `thinking_delta` / `tool_delta` 流式事件、Gemini 的 contents/parts 结构与 base64/URL 双模式图片、百炼的 wan2.6 多种生图协议 + 异步任务轮询。内置厂商模型清单见 `service/catalog.py`，前端「导入预设」即消费它。

### 6 种 AI 能力 + 6 条 Celery 队列

| AI 能力 | Celery 队列 | 状态 |
|---------|-------------|------|
| Chat 对话（同步 + SSE 流式） | `ai.chat` | 已实现 |
| Image 生图（同步线程池 + 异步任务） | `ai.image` | 已实现 |
| Embedding | `ai.embedding` | 已实现 |
| Rerank | `ai.rerank` | 已实现 |
| Audio | `ai.audio` | 接口与队列已定义，适配器实现尚不完整 |
| Video | `ai.video` | 接口与队列已定义，适配器实现尚不完整 |

SSE 流式以 `start` / `delta` / `done` / `error` 事件下发。队列可独立扩缩容：AI 密集场景多开 `ai.chat` / `ai.image` worker，工作流密集多开 `workflow` worker。

## 企业级治理与安全

### 治理三维

| 维度 | 取值 |
|------|------|
| 范围 | `global` / `user` / `profile` |
| 周期 | `minute` / `day` / `month` |
| 模式 | `enforce`（拦截） / `observe`（观察） |

### 四维限流

请求 / 并发 / Token / 成本四个维度均可配额，超限触发告警事件（`AiGovernanceEvent`）。治理规则由 `AiGovernanceRule` 维护，由 `governance_service.py` 在每次调用前后强制检查。

### 安全能力

- **提示注入检测**：输入侧 DoS 防护（长度上限）+ 提示注入检测。
- **PII 脱敏**：输出侧对手机 / 身份证 / 邮箱自动脱敏（工作流内部数据可 `skip_masking=True` 跳过）。
- **密钥加密**：厂商 API Key 使用 PBKDF2 + 加密存储，前端只回显脱敏串。
- **会话并发控制**：`ADMIN_SESSION_MAX_CONCURRENT` 限制同一用户最大并发会话，配合 JWT + Token 吊销。
- **CSRF Origin 校验**：`ADMIN_CSRF_ORIGIN_CHECK_ENABLED` 控制管理端变更请求的 Origin/Referer 校验。
- **密码哈希升级**：`PASSWORD_PBKDF2_ITERATIONS` 配置迭代次数，登录成功后自动升级旧哈希。

## 可观测与计费

### 调用日志与计量

每次 AI 调用记录到 `AiModelCallLog`，含延迟（`latency_ms`）、Token、成本字段。**成本统一以微美元 `cost_micro_usd` 计量**（1 USD = 1,000,000 micro_usd），跨厂商可比。用量看板接口 `/admin/ai/dashboard/cost` 支持按天 / 按维度分组聚合。

### 三类审计日志

- **操作日志**：管理端变更类操作流水。
- **登录日志**：登录成功 / 失败记录。
- **安全日志**：限流触发、CSRF 拦截、Token 吊销等安全事件。

### 健康检查与指标

- `/health`：返回数据库、Redis、Celery 配置检查。
- `/metrics`：文本指标端点，由 `METRICS_ENABLED` 控制开关，默认关闭。

### Celery Beat 三项定时任务

| 任务 | 周期 | 职责 |
|------|------|------|
| `task.dispatch_due_system_tasks` | 每分钟 | 扫描启用且到期的系统任务并派发执行 |
| `clean-expired-logs-daily` | 每天 02:00 | 清理过期任务日志 |
| `clean-expired-ai-governance-data-daily` | 每天 03:00 | 清理过期治理数据 |

## 通用任务调度

`task` 模块是**通用系统定时任务调度器**，不是 AI / 工作流任务的「信封」——它不记录 `celery_task_id` / `progress` 等运行态字段，与 AI / 工作流没有直接外键耦合，是平行的通用能力。

- **触发模型**：cron（五段表达式）或固定间隔（`every` 毫秒）。
- **保守调度器**：自行计算下次运行时间，调度状态缓存到 Redis（`task:schedule` 命名空间）。
- **Celery Beat 扫描**：每分钟扫描启用且到期的任务，派发到 `default` 队列执行。
- **反射执行**：按 `service` 字段中的方法路径反射调用业务方法，传入 `data` 参数。
- **运维接口**：`start` / `stop` / `once` 提供启停与立即执行；`TaskLog` 记录每次执行结果。
- **通知配置**：成功 / 失败 / 超时均可配置通知收件人与模板。

典型用途：给工作流定义做定时触发、定时跑数据加工、定时清理等。

## 通知 / 媒体 / 字典 / 权限

- **通知系统**：站内 / 业务 / 任务通知 + 模板化发送，详见 [通知系统框架说明](./docs/通知系统框架说明.md)。
- **媒体资源**：本地与 S3-compatible 文件存储统一抽象，由 `STORAGE_PROVIDER` 与 `S3_*` 配置切换。
- **字典管理**：枚举值集中维护，前端通过 EPS 自动消费。
- **权限管理**：JWT + 动态菜单 + 细粒度 Action 权限校验 + DataScope 数据权限，详见 [权限管理与登录模块设计](./docs/权限管理与登录模块设计.md)。

## 示例工作流

`examples/workflows/` 下提供可导入的工作流样例，便于快速上手：

- [基础 QA 工作流](./examples/workflows/01_Basic_QA_Workflow.json)：最简单的 LLM 单节点范例，演示 start → llm → end 的基础文本生成。
- [Agent 工具协同工作流](./examples/workflows/03_Agent_Tool_Workflow.json)：演示 tool_executor 调用外部工具（联网搜索）→ llm 整理答案的智能体协同模式。

其余示例覆盖意图路由、循环处理、条件分支、批处理、变量操作等场景，可直接在工作流编辑器导入体验。

## 快速开始

### 使用 Docker Compose（推荐）

1. 复制环境变量文件：

```bash
cp .env.example .env
```

2. 编辑 `.env`，填入 OpenAI API Key 或配置本地 Ollama 等厂商凭证。

3. 启动所有服务：

```bash
docker-compose up -d
```

4. 访问应用：
- 前端：http://localhost:9090
- 后端 API：http://localhost:8000
- API 文档：http://localhost:8000/docs
- Redoc：http://localhost:8000/redoc

### 本地开发

#### 后端

1. 创建 Python 虚拟环境并安装依赖：

```bash
cd backend
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate
pip install -r requirements.txt
```

2. 配置环境变量：

```bash
cp .env.example .env
# 编辑 .env 配置 API Key、数据库、Redis 等
```

3. 启动 FastAPI 服务：

```bash
uvicorn main:app --reload
```

4. 启动 Celery Worker（新终端）。队列可按需选择，全量场景建议同时消费多个队列：

```bash
cd backend
celery -A app.celery_app worker --loglevel=info -Q workflow,ai.chat,ai.image,default
```

5. 启动 Celery Beat（可选，启用定时任务调度时需要）：

```bash
celery -A app.celery_app beat --loglevel=info
```

#### 前端

1. 安装依赖：

```bash
cd frontend
npm install
```

2. 启动开发服务器（端口 9090）：

```bash
npm run dev
```

## 项目结构

```
Loom/
├── frontend/                      # Vue 3 前端
│   ├── src/
│   │   ├── cool/                  # 框架核心、service、router、bootstrap
│   │   ├── modules/               # 业务模块（ai / base / dict / media / notification / task / workflow 等）
│   │   ├── plugins/               # 项目插件
│   │   └── config/                # 环境与代理配置
│   ├── packages/                  # 本地源码包（@cool-vue/crud 等）
│   └── tests/                     # Vitest 单元测试与 Playwright E2E
├── backend/                       # FastAPI 后端
│   ├── app/
│   │   ├── core/                  # 配置、数据库、安全、Redis、日志
│   │   ├── framework/             # 自动路由、EPS、中间件、查询构建
│   │   └── modules/               # 业务模块（见下表）
│   ├── tests/                     # pytest 自动化测试
│   └── alembic/                   # 数据库迁移骨架
├── docs/                          # 项目文档（见文末索引）
├── examples/workflows/            # 示例工作流 JSON
├── scripts/                       # 本地验证脚本
├── docker-compose.yml
└── README.md
```

### 后端业务模块（`backend/app/modules/`）

| 模块 | 职责 |
|------|------|
| `ai` | 厂商/模型/调用配置管理、12 家厂商适配、统一运行时、治理安全、计费可观测 |
| `base` | 权限 / 认证 / 菜单 / 部门 / 角色等基础能力 |
| `dict` | 字典枚举管理 |
| `media` | 媒体资源与本地 / S3-compatible 文件存储 |
| `notification` | 站内 / 业务 / 任务通知与模板 |
| `task` | 通用系统定时任务调度器（cron / 间隔 + Beat 扫描 + 反射执行） |
| `workflow` | 基于 LangGraph 的可视化工作流编排引擎 |
| `workflow_annotation` | 人工标注队列与 κ 校准 |
| `workflow_eval` | 工作流评测与回归对比 |

### 前端业务模块

`frontend/src/modules/` 下对应 `ai` / `base` / `dict` / `media` / `notification` / `task` / `workflow` 等模块的页面、store、service 与静态资源。AI 模块包含对话测试台（SSE 流式）、生图工作台、厂商/模型/配置管理、治理规则/事件、看板、日志、异步任务等 10 个页面；工作流模块包含 Vue Flow 编辑器、节点配置面板、试运行 / 单节点测试 / 实时日志抽屉、实例管理（含人工审批恢复）。

### 示例与文档

- `examples/workflows/`：10 个示例工作流 JSON，覆盖基础 QA、意图路由、Agent 工具协同、循环、批处理、条件分支、变量操作等场景。
- `docs/`：项目文档全集，详见文末[完整文档](#完整文档)。

## 框架能力概览

Loom 后端框架层提供以下基础能力，每项均不展开实现细节，详细规范见 `docs/` 下对应文档：

- **模块化架构**：模块自治，独立中间件、白名单、数据初始化与菜单注入，详见 [框架说明文档](./docs/框架说明文档.md)。
- **自动路由**：按目录约定扫描 `controller/{scope}/` 自动注册路由，URL 遵循 `/{scope}/{module}/{resource}/{action}`，详见 [模块自动路由与管理端鉴权说明](./docs/模块自动路由与管理端鉴权说明.md)。
- **声明式 CRUD 控制器**：`@CoolController` 装饰器自动注册 add/delete/update/info/list/page 等标准接口，详见 [框架Controller使用规范](./docs/框架Controller使用规范.md)。
- **EPS 元数据**：自动扫描模型字段与验证规则导出，驱动前端表单/表格/验证自动生成，详见 [EPS规范原理与操作指南](./docs/EPS规范原理与操作指南.md)。
- **数据权限**：`DataScope` 在查询时自动注入权限过滤（全部 / 本人 / 本部门 / 本部门及下属 / 自定义），详见 [权限管理与登录模块设计](./docs/权限管理与登录模块设计.md)。
- **软删除**：模型含 `delete_time` 字段时自动过滤已删除记录，删除时按元数据配置选择 `UPDATE` 或 `DELETE`。
- **字段映射**：内部 snake_case ↔ API camelCase 自动转换，关键全局别名如 `created_at→createTime` / `is_active→status` / `component→viewPath` / `path→router`，详见 [字段映射使用规范](./docs/字段映射使用规范.md)。
- **缓存命名空间与降级**：Redis 缓存按命名空间隔离，开发模式自动降级为进程内缓存，详见 [框架说明文档](./docs/框架说明文档.md)。

## API 规范与兼容性

本项目后端 API 面向 Loom 管理端前端设计，统一输出 `{ code, message, data }` 响应结构，并通过 EPS 元数据驱动前端 service、表格和表单。

### 命名规范

路由遵循 `/{scope}/{module}/{resource}/{action}` 结构：

| scope | 说明 |
|-------|------|
| `admin` | 管理后台接口 |
| `app` | 移动端 / 用户端接口 |
| `aiapi` | AI 开放接口（对应 `/aiapi/ai/model/*`） |
| `open` | 开放接口 |

- **module**：业务模块名，如 `base`（权限）、`ai`（AI 模型）、`workflow`（工作流）、`task`（任务）、`dict`（字典）。
- **resource**：资源标识，如 `sys/user`、`sys/role`、`ai/model`。
- **action**：动作指令，对应 `BaseAdminCrudService` 提供的标准操作或自定义接口。

### 标准 CRUD 动作

所有基于 `BaseController` 开发的资源默认具备以下动作：

| 动作 | 方法 | 描述 |
|------|------|------|
| `add` | POST | 新增记录 |
| `delete` | POST | 批量删除记录 |
| `update` | POST | 更新记录 |
| `info` | GET | 获取单条详情 |
| `list` | GET / POST | 获取全量列表，POST 为主协议，GET 为兼容入口 |
| `page` | GET / POST | 获取分页列表（支持高级搜索），POST 为主协议，GET 为兼容入口 |

### 完整文档

项目启动后，可访问以下路径查看实时 API 文档：
- API 文档：http://localhost:8000/docs
- Redoc：http://localhost:8000/redoc
- 项目说明文档索引：[docs/README.md](./docs/README.md)

## 环境变量

### 后端

- `DATABASE_URL`：数据库连接字符串
- `REDIS_URL`：Redis 连接字符串
- `JWT_SECRET_KEY`：JWT 密钥，建议至少 32 字节
- `OPENAI_API_KEY` / `OPENAI_BASE_URL`：OpenAI 默认凭证（用于早期兼容，生产应通过厂商配置管理）
- `CORS_ORIGINS` / `CORS_ALLOW_METHODS` / `CORS_ALLOW_HEADERS`：CORS 白名单
- `ADMIN_CSRF_ORIGIN_CHECK_ENABLED`：管理端变更请求 Origin/Referer 校验开关
- `RESPONSE_ENVELOPE_MAX_BYTES`：统一响应包装最大 JSON 体积，超出后跳过包装
- `MODULE_LOAD_STRICT`：模块加载失败时是否中断启动
- `PASSWORD_PBKDF2_ITERATIONS`：PBKDF2 密码哈希迭代次数，登录成功后自动升级旧哈希
- `ADMIN_SESSION_MAX_CONCURRENT`：管理端同一用户最大并发会话数，`0` 表示不限制
- `STORAGE_PROVIDER` 与 `S3_*`：本地或 S3-compatible 文件存储配置
- `METRICS_ENABLED`：是否记录并开放 `/metrics` 文本指标
- `DB_POOL_*`：非 SQLite 数据库连接池参数
- `API_VERSION_PREFIX_ENABLED`：是否额外挂载 `/api/v1` 兼容前缀

### 前端

- `VITE_API_BASE_URL`：后端 API 基础 URL

### 工作流

- `WORKFLOW_CHECKPOINT_BACKEND`：工作流 Checkpoint 后端，取值 `memory` / `sqlite` / `postgres`。开发默认 `memory`，audit S3 后默认 `sqlite`，生产建议 `postgres`。
- 其他 `WORKFLOW_*`：节点级超时、单节点测试去重窗口、批处理并发上下界等运行时参数，详见 [AI 与工作流系统架构说明](./docs/AI与工作流系统架构说明.md)。

## 完整文档

完整文档索引见 [docs/README.md](./docs/README.md)，关键文档包括：

- [AI 与工作流系统架构说明](./docs/AI与工作流系统架构说明.md)：AI 模块、工作流模块、task 模块的完整架构与集成关系。
- [评测系统对标分析-2026-06-26](./docs/评测系统对标分析-2026-06-26.md)：工作流评测系统能力边界与提升路线图。
- [框架说明文档](./docs/框架说明文档.md)：模块化、自动路由、EPS、DataScope 等核心机制。
- [模块自动路由与管理端鉴权说明](./docs/模块自动路由与管理端鉴权说明.md)：路由约定与权限校验。
- [EPS规范原理与操作指南](./docs/EPS规范原理与操作指南.md)：EPS 元数据协议。
- [字段映射使用规范](./docs/字段映射使用规范.md)：snake_case ↔ camelCase 字段映射。
- [框架Controller使用规范](./docs/框架Controller使用规范.md) / [框架Service使用规范](./docs/框架Service使用规范.md) / [框架Model使用规范](./docs/框架Model使用规范.md)：CRUD 与建模规范。
- [权限管理与登录模块设计](./docs/权限管理与登录模块设计.md)：JWT、动态菜单、数据权限。
- [通知系统框架说明](./docs/通知系统框架说明.md)：通知与模板。
- [自动化测试使用说明](./docs/自动化测试使用说明.md)：pytest / 单元测试 / E2E。

## 开源协议

本项目采用 [MIT License](./LICENSE) 协议开源。
