# Loom AI 与工作流系统架构说明

> 本文以**当前主干代码**为准，系统说明后端 `ai`、`workflow`、`task` 三个模块与对应前端的架构设计、集成关系与边界。
>
> 适用范围：Loom 主干（FastAPI + SQLModel + Celery + Vue3）。如发现描述与代码不符，以代码为准，并请同步修订本文档。
>
> 关于本架构说明与其他（已废弃/失真）分析版本的差异，见文末[附录 A](#附录-a与其他分析版本的差异说明)。

---

## 一、系统全景

Loom 的 AI 能力与工作流编排由**三个后端模块 + 两块前端**构成，统一以 **Celery + Redis** 为异步执行与事件骨干：

| 模块 | 后端路径 | 前端路径 | 定位 |
|------|----------|----------|------|
| **ai** | `backend/app/modules/ai/` | `frontend/src/modules/ai/` | 厂商/模型/调用配置管理、多厂商适配、统一运行时、治理安全、计费可观测 |
| **workflow** | `backend/app/modules/workflow/` | `frontend/src/modules/workflow/` | 基于 **LangGraph** 的可视化工作流编排引擎，消费 AI 能力 |
| **task** | `backend/app/modules/task/` | — | **通用系统定时任务调度器**（cron/间隔触发），非 AI 任务信封 |

三者关系：**ai 是能力提供方，workflow 是能力消费方，task 是与业务解耦的通用定时调度框架**。workflow 不直接接触厂商 API，而是通过 `profile_code` 引用 ai 模块的统一运行时；task 可用于给 workflow 等业务做定时触发。

```
┌─────────────── 前端 ───────────────┐    ┌─────────────── 后端 ───────────────┐
│ modules/ai                         │    │ modules/ai                         │
│  · 厂商/模型/配置管理 (CRUD)         │◀──▶│  · 三层配置 Provider/Model/Profile  │
│  · 对话/生图工作台 (SSE 流式)        │    │  · 适配器层 (12+ 厂商)              │
│  · 治理/日志/看板/任务               │    │  · AiModelRuntimeService 统一运行时 │
├────────────────────────────────────┤    ├────────────────────────────────────┤
│ modules/workflow                   │    │ modules/workflow                   │
│  · Vue Flow 可视化编辑器             │◀──▶│  · compiler.py (拓扑→LangGraph)     │
│  · 16 种节点 + 配置面板              │    │  · Celery 异步 + Checkpoint 持久化  │
│  · 试运行/单节点测试/实时日志        │    │  · Redis pub/sub 事件总线 + SSE     │
└────────────────────────────────────┘    └────────────────────────────────────┘
                          ▲
                          │  AI 能力以 Profile 抽象暴露
                          └──── workflow 的 llm/image/intent 节点调用 ai 运行时
```

---

## 二、AI 模块（后端）

### 2.1 三层配置架构（核心设计）

[`model/ai.py`](../backend/app/modules/ai/model/ai.py) 通过清晰的三层抽象隔离「凭证 / 模型 / 调用参数」：

| 层级 | 实体 | 职责 | 关键字段 |
|------|------|------|----------|
| **Provider 厂商** | `AiProvider` | 接入凭证 + base_url | `adapter`（适配器类型）、`api_key_cipher`（加密密钥）、`api_key_mask`（脱敏展示）、`extra_config` |
| **Model 模型** | `AiModel` | 模型能力与定价 | `provider_id`、`model_type`、`context_window`、`max_output_tokens`、`pricing_config` |
| **Profile 调用配置** | `AiModelProfile` | 业务侧调用参数 | `code`、`scenario`、`temperature`、`response_format`、`retry_count`、`fallback_profile_id`、`is_default` |

要点：
- 厂商密钥**集中加密存储**（`api_key_cipher`），前端只回显脱敏串 `api_key_mask`。
- **Profile 是业务唯一入口**：业务侧只认 `profile_code`，厂商/模型变更对调用方透明。
- 支持配置级**兜底**（`fallback_profile_id`）：主配置失败可自动降级。

其余实体：`AiModelCallLog`（调用日志，含 `latency_ms` / `tokens` / `cost_micro_usd`）、`AiGenerationTask`（异步生成任务）、`AiGovernanceRule` / `AiGovernanceEvent`（治理）、`AiRuntimeInvocation`（运行时调用追踪）。

### 2.2 多厂商适配器层（策略 + 工厂）

[`service/adapters/factory.py`](../backend/app/modules/ai/service/adapters/factory.py) 用工厂模式统一了 **12 家厂商**：

`openai-compatible`、`ollama`、`gemini`、`claude`、`deepseek`、`volcengine-ark`（火山方舟）、`bailian`（阿里百炼）、`hunyuan`（腾讯混元）、`qianfan`（百度千帆）、`zhipu`（智谱）、`minimax`、`mimo`（小米）

适配器基类 [`base.py`](../backend/app/modules/ai/service/adapters/base.py) 统一了 `chat/stream_chat/embedding/image/audio/video/rerank/test/list_models` 接口。代表性特殊处理：
- **Claude**（[`claude.py`](../backend/app/modules/ai/service/adapters/claude.py)）：`x-api-key` 认证、system 消息独立、支持 `thinking_delta`/`tool_delta` 流式事件。
- **Gemini**（[`gemini.py`](../backend/app/modules/ai/service/adapters/gemini.py)）：`x-goog-api-key`、contents/parts 结构、base64/URL 双模式图片。
- **百炼**：wan2.6 多种生图协议 + 异步任务轮询。

> 内置厂商模型清单见 [`service/catalog.py`](../backend/app/modules/ai/service/catalog.py)，前端「导入预设」即消费它。

### 2.3 统一运行时（调度中枢）

[`service/runtime_service.py`](../backend/app/modules/ai/service/runtime_service.py) 中的 `AiModelRuntimeService` 是 AI 模块的心脏。`_invoke` 串联完整调用链：

```
治理检查(begin) → 构建适配器 → 重试调用 → 成本计算 → 治理完成(finish) → 写调用日志 → 输出脱敏 → 失败兜底(fallback)
```

对外暴露 6 种能力，对应 6 个独立 Celery 队列（`ai.chat` / `ai.image` / `ai.embedding` / `ai.rerank` / `ai.audio` / `ai.video`）：
- **Chat 对话**：同步 + SSE 流式（`start`/`delta`/`done`/`error` 事件）。
- **Image 生图**：同步线程池 + 异步任务双模式。
- **Embedding / Rerank**：已实现。
- **Audio / Video**：接口与队列已定义，适配器实现尚不完整（见[第六节改进项](#七已知局限与改进方向)）。

> ⚠️ `service/ai_service.py` **不是服务入口**，而是**兼容导出层**（见文件头注释：实现已按职责拆分到各服务模块，仅保留供旧 import 兼容）。真正的核心服务是 `AiModelRuntimeService`。请勿在此文件新增逻辑。

### 2.4 治理与安全（企业级特性）

- **治理** [`service/governance_service.py`](../backend/app/modules/ai/service/governance_service.py)：支持 `global/user/profile` 三级范围、`minute/day/month` 周期、`enforce`（拦截）/`observe`（观察）模式，可限**请求/并发/Token/成本**，超限触发告警事件。
- **安全** [`service/security_service.py`](../backend/app/modules/ai/service/security_service.py)：输入侧 DoS 防护（长度上限）+ 提示注入检测；输出侧 PII 脱敏（手机/身份证/邮箱）。

### 2.5 可观测与计费

- 调用日志 `AiModelCallLog` 记录每次调用的延迟、Token、成本，**成本统一以微美元 `cost_micro_usd` 计量**（1 USD = 1,000,000 micro_usd）。
- 用量看板接口 `/admin/ai/dashboard/cost`，支持按天/按维度分组。
- 清理：`ai.clean_expired_governance_data`（每天 3 点，Celery Beat）。

---

## 三、工作流模块（后端）

### 3.1 数据模型

[`model/workflow.py`](../backend/app/modules/workflow/model/workflow.py) 三张核心表：

| 实体 | 职责 | 关键字段 |
|------|------|----------|
| `WorkflowDefinition` | 工作流蓝图 | `code`、`graph_json`（拓扑 JSON）、`is_active`、`user_id`（数据权限隔离） |
| `WorkflowInstance` | 单次运行实例 | `definition_id`、`thread_id`（LangGraph checkpoint 隔离）、`status`（pending/running/paused/success/failed/cancelled）、`state_data`（变量快照）、`celery_task_id` |
| `WorkflowExecutionLog` | 节点级执行日志 | `instance_id`、`node_id`、`input_data`、`output_data`、`latency_ms`、`status` |

### 3.2 编译器：拓扑 → LangGraph（核心）

这是整个工作流最有技术含量的部分。[`service/compiler.py`](../backend/app/modules/workflow/service/compiler.py) 把前端画布拓扑**编译成 LangGraph StateGraph**：

```
validate_graph(拓扑校验) → 递归编译子图(loop/batch) → 主图 add_node → add_edge → 条件分流 add_conditional_edges
```

`validate_graph` 前置校验：缺 START 节点、悬空/重复边、子图路由、孤立节点、**静态环路检测（DFS）**、模型节点配置完整性。

节点分类（影响编译策略）：
- **条件分流** `condition`/`intent_classifier`/`switch`：出边由运行时路由决定，不参与静态环检测。
- **子图执行** `loop_controller`/`batch_processor`：编译期提取为独立子图，运行时按序/并发调用。

### 3.3 节点系统（16 种）

节点执行器通过 `NodeExecutorRegistry` 注册（`(state, config) -> dict`，可扩展）。已注册 13 个执行器，集中定义于 [`service/workflow_service.py`](../backend/app/modules/workflow/service/workflow_service.py)：

| 类别 | 节点 |
|------|------|
| 基础 | `start` / `end` |
| AI | `llm` / `image_generator` / `intent_classifier` |
| 逻辑 | `condition`（T/F 双端口）/ `switch`（动态端口）/ `loop_controller` / `batch_processor` |
| 系统 | `tool_executor` / `human_input` / `variable_assignment` / `variable_transform` / `tool`（旧） |
| 容器 | `loop_body_group` |

代表性执行器：
- **LLM 节点**：分层 JSON 输出（Tier1 `json_schema` / Tier2 `json_object` / Tier3 纯文本）。
- **循环控制器**：状态链式循环（上一次输出作为下次输入）。
- **批处理**：`asyncio.gather + Semaphore` 控制并发（限 1–20）。
- **人工交互**：用 LangGraph 原生 `interrupt` 挂起，靠 checkpoint 恢复。

### 3.4 执行引擎与 Celery 异步化

- **Celery 化**：[`tasks/workflow_tasks.py`](../backend/app/modules/workflow/tasks/workflow_tasks.py) 将执行从 Web 进程剥离，任务名 `workflow.execute`，路由到 `workflow` 队列，节点级超时可配，硬上限 30 分钟。
- **服务层** [`service/workflow_service.py`](../backend/app/modules/workflow/service/workflow_service.py)：`WorkflowService`（定义 CRUD + 校验）、`WorkflowInstanceService`（启动/恢复/取消/单节点测试，含原子 CAS 与防重放）。

### 3.5 Checkpoint 持久化

[`service/checkpointer.py`](../backend/app/modules/workflow/service/checkpointer.py) 支持 `memory` / `sqlite` / `postgres` 三种后端（由 `WORKFLOW_CHECKPOINT_BACKEND` 配置）。这是**人工交互挂起/恢复**的基础——`human_input` 节点 `interrupt` 后，状态落入 checkpoint，恢复时 `Command(resume=...)` 继续。

### 3.6 事件总线与 SSE

[`service/event_bus.py`](../backend/app/modules/workflow/service/event_bus.py) 用 **Redis pub/sub** 跨进程推送节点执行事件；实例控制器 `/admin/workflow/instance/stream` 以 **SSE** 实时下发到前端。

### 3.7 变量与表达式系统

- **模板渲染**：[`compiler.py`](../backend/app/modules/workflow/service/compiler.py) 的 `render_template` 支持 `{var}` / `{var.field}` / `{var.list.0}` 语法。
- **安全求值**：自研 `SafeEvaluator`（AST 白名单，防条件表达式代码注入）。
- **输入/输出映射**：节点可声明 `inputs` schema（变量名 + 类型 + 上游引用 source）实现严格数据流；未声明则透传全局变量。

### 3.8 健壮性设计

- **原子 CAS 状态机**：`resume`/`cancel` 用 `UPDATE ... WHERE status=?` 消除 TOCTOU 竞态。
- **防重放**：启动 2 秒去重、单节点测试 Redis 去重（429）。
- **稳定 Handle ID**：前端 `genId()` + 后端 `case_${stableId}`，解决删除中间分支导致连线错位。
- **数据权限**：`assert_workflow_owner` 限定非超管只能操作本人工作流。

---

## 四、任务模块（后端，task）

> ⚠️ **重要澄清**：`task` 模块是**通用系统定时任务调度器**，**不是** AI/工作流任务的「信封」。它的设计参考 Midway 的 job 系统（`TaskInfo.job_id` 字段注释明确写「对应 Midway 的 jobId」）。

### 4.1 数据模型（[`model/task.py`](../backend/app/modules/task/model/task.py)）

- `TaskInfo`（表 `task_info`）：调度元信息。核心字段 `name`、`job_id`、`cron`（cron 表达式）、`every`（间隔毫秒）、`task_type`（0 cron / 1 间隔）、`service`（**要执行的方法路径**）、`data`（参数 JSON）、`next_run_time`、`last_execute_time`、`status`（0 停止 / 1 运行）、通知配置（成功/失败/超时通知 + 收件人 + 模板）。
- `TaskLog`（表 `task_log`）：每次执行结果（status、detail、consume_time）。

### 4.2 调度机制（[`service/task_service.py`](../backend/app/modules/task/service/task_service.py) + [`tasks/system_tasks.py`](../backend/app/modules/task/tasks/system_tasks.py)）

- **触发模型**：cron（五段表达式）或固定间隔（`every` 毫秒）。
- **保守调度器**：`compute_next_run_time` / `compute_next_cron_run_time` 自行计算下次运行时间，调度状态缓存到 Redis（`task:schedule` 命名空间）。
- **Celery Beat 扫描**：`task.dispatch_due_system_tasks` **每分钟**扫描启用且到期的任务 → `task.execute_system_task` 执行。
- **反射执行**：[`service/task_invoker.py`](../backend/app/modules/task/service/task_invoker.py) 按 `service` 方法路径反射调用业务方法，传入 `data` 参数。
- **运维**：`task.clean_expired_logs` 每天 2 点清理过期日志；`start`/`stop`/`once` 提供启停与立即执行。

### 4.3 与 AI/工作流的关系

`task` 模块与 AI/工作流**没有直接的外键耦合**，是平行的通用能力。它可被用于：给工作流定义做定时触发、定时跑数据加工、定时清理等。它**不**记录 `celery_task_id` / `progress` 等运行态字段——这些是它作为「调度器」而非「运行跟踪器」的边界。

---

## 五、Celery 整体架构

[`backend/app/celery_app.py`](../backend/app/celery_app.py)：

- **Broker / Backend**：Redis。
- **队列**：`celery`、`default`、`workflow`、`ai.chat`、`ai.image`、`ai.embedding`、`ai.rerank`、`ai.audio`、`ai.video`。
- **路由**：`workflow.execute`→`workflow`、`ai.execute_generation_task`→`ai.chat`、系统任务（`task.*`）与治理清理统一→`default`。
- **可靠性**：`task_acks_late=True`（完成后确认，防 worker 崩溃丢失）、`worker_prefetch_multiplier=1`（公平调度）。
- **Celery Beat 定时任务**：
  - `dispatch_due_system_tasks`：每分钟扫描到期任务。
  - `clean-expired-logs-daily`：每天 02:00 清理过期日志。
  - `clean-expired-ai-governance-data-daily`：每天 03:00 清理过期治理数据。

> 队列可独立扩缩容：AI 密集场景多开 `ai.chat`/`ai.image` worker，工作流密集多开 `workflow` worker。

---

## 六、前端

### 6.1 AI 管理（[`frontend/src/modules/ai/`](../frontend/src/modules/ai/)）

10 个页面：对话测试台（`chat.vue`，SSE 流式）、生图工作台（`image.vue`，智能厂商检测）、厂商/模型/配置管理、治理规则/事件、看板、日志、异步任务。运行时调用集中在 [`service/runtime.ts`](../frontend/src/modules/ai/service/runtime.ts)，对接 `/aiapi/ai/model/*`。

### 6.2 工作流编辑器（[`frontend/src/modules/workflow/views/editor.vue`](../frontend/src/modules/workflow/views/editor.vue)）

基于 **@vue-flow/core** 的可视化编辑器：
- **16 种节点** + 统一基础节点 + 配置面板（`node-config-panel.vue`）。
- **三级变量体系**（全局上游 / 循环上下文 / 局部输入）+ 变量选择器（`cl-variable-input.vue`）。
- **调试**：试运行（`useWorkflowTest.ts`，递增延迟轮询）、单节点测试（`useNodeTest.ts`，令牌防并发）、实时日志抽屉。
- **稳定 Handle**：`genId()` 生成稳定端口 id，解决删分支连线错位。
- 管理页：工作流定义列表、实例管理（含人工审批恢复）。

---

## 七、模块集成关系（关键链路）

工作流消费 AI 能力的完整链路：

```
前端 LLM 节点配置 (modelProfileCode="gpt-4")
        ↓ 保存到 graph_json
后端 compiler 编译 → execute_llm_node (workflow_service.py)
        ↓ 调用 run_ai_chat()
        ↓ AiModelRuntimeService(session).chat()  ← 复用 AI 模块运行时
        ↓ 经过 治理检查 → 适配器 → 重试 → 成本计算 → 日志
   返回 content → 写入 output_variable → 下游节点引用
```

**关键点**：工作流**复用 AI 模块的全部治理、安全、日志、计费能力**，不重复造轮子。`run_ai_chat` 以 `skip_masking=True` 跳过脱敏（工作流内部数据），并做空响应拦截防御。

---

## 八、设计亮点

1. **Profile 抽象**：业务侧只认 `profile_code`，厂商/模型变更对调用方透明。
2. **LangGraph 编译型引擎**：拓扑校验前置，运行期是编译后的 StateGraph，比解释执行更可靠。
3. **复用而非重复**：工作流直接复用 AI 运行时，治理/计费天然贯通。
4. **企业级治理安全**：多维度限流 + 提示注入检测 + PII 脱敏 + 密钥加密 + 兜底。
5. **工程健壮性**：CAS 状态机、稳定 Handle、安全求值、防重放、checkpoint 持久化。
6. **通用定时调度**：`task` 模块与业务解耦，cron/间隔 + Beat 扫描 + Redis 缓存，可复用于任意业务定时需求。

---

## 九、已知局限与改进方向

| 项 | 现状 | 建议 |
|----|------|------|
| **Audio/Video 适配器空缺** | 接口与队列已定义，适配器矩阵基本未实现 | 落地具体厂商逻辑 |
| **工作流流式输出** | 试运行为轮询，非真正 SSE | 接 Redis pub/sub → WebSocket/SSE 逐字下发 |
| **`graph_json` 双写** | 前端存 `elements`/`nodes`/`edges` 三份近似数据 | 评估收敛为单一权威结构 |
| **会话历史** | AI 模块不维护多轮会话，需调用方传完整 messages | 按需引入会话管理 |
| **`parallel` 能力** | 批处理已有并发，但 DAG 中独立分支目前仍按拓扑串行推进 | 评估并行执行独立分支 |

---

## 附录 A：与其他分析版本的差异说明

> 本节用于钉死分歧，避免后人混淆。存在一份**与当前主干代码严重不符**的分析版本（疑似幻觉或极早期草稿），其核心结论**均未被本文采用**。逐条对比如下：

| 主题 | 失真版本声称 | 主干代码实际（本文依据） |
|------|--------------|--------------------------|
| AI 入口服务 | `AIService.execute_task()` 为总入口，`RuntimeService.execute(task_id)` 执行 | `ai_service.py` 是**兼容导出层**（仅 re-export，无业务逻辑）；核心为 `AiModelRuntimeService` |
| Provider 字段 | `provider_type` 字段 | 实际字段为 `adapter` |
| 适配器数量 | 4 种（OpenAI/Claude/Gemini/Ollama）+ OpenAIHTTP | **12 家**厂商适配器 |
| 工作流引擎 | 自研 `WorkflowEngine` + 5 个 service（definition/instance/node/execution/engine） | 基于 **LangGraph**，service 为 `compiler`/`workflow_service`/`checkpointer`/`event_bus` |
| 工作流控制器 | `definition`/`instance`/`execution`/`node` 四个 | 仅 `definition`/`instance` 两个 |
| 工作流节点 | 9 种：`ai_generation`/`condition`/`transform`/`notification`/`human_review`/`api_call`/`delay`/`parallel`/`sub_workflow` | **16 种**：`start`/`end`/`llm`/`image_generator`/`intent_classifier`/`condition`/`switch`/`loop_controller`/`batch_processor`/`tool_executor`/`human_input`/`variable_assignment`/`variable_transform`/`loop_body_group`/`tool`(旧) |
| Celery 队列 | `ai_generation` / `workflow` 两队列 | `celery`/`default`/`workflow` + `ai.chat`/`ai.image`/`ai.embedding`/`ai.rerank`/`ai.audio`/`ai.video` |
| Celery Beat | 「未发现定时调度逻辑」 | **存在**：每分钟扫描任务、每天清理日志/治理数据 |
| task 模块 | 「通用任务信封」，含 `task_status`/`celery_task_id`/`progress`/`params`/`result` 字段 | **系统定时任务调度器**，字段为 `job_id`/`cron`/`every`/`task_type`/`service`/`next_run_time` 等；上述「信封」字段不存在 |

**结论**：失真版本描述的架构（`AIService` + 自研 `WorkflowEngine` + 9 节点 + `ai_generation` 队列 + task 信封）在当前主干代码中**不存在**，应为早期设计草稿（已被重构为 LangGraph 版本）或生成失真。任何据此版本的二次开发都将落空，请一律以本文及实际代码为准。
