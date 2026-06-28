# Workflow 模块代码审查报告

> **审查日期**：2026-06-22
> **审查范围**：工作流模块全量（后端 compiler / 执行服务 / 接口安全 + 前端画布 / 节点配置，约 12K 行）
> **审查方法**：5 维度并行审查 → 对每条严重项回到源码对抗验证 → 剔除误报
> **覆盖文件**：`backend/app/modules/workflow/**`、`frontend/src/modules/workflow/**`

## 状态图例

| 标记 | 含义 |
|---|---|
| 【未修复】 | 已确认的问题，尚未处理 |
| 【已修复】 | 已完成修复（修复后请更新标记并补 commit 号） |
| 【误报】 | 经源码复核判定不成立，仅作记录 |

## 修复进度总览

| 编号 | 严重度 | 标题 | 状态 |
|---|---|---|---|
| S1 | 🔴 严重 | 工作流实例全量无所有者隔离（IDOR） | 【已修复】 |
| S2 | 🔴 严重 | PII 脱敏被关闭 + 用户输入原样落库 | 【已修复】 |
| S3 | 🔴 严重 | 默认 checkpointer 是 MemorySaver | 【已修复】 |
| S4 | 🔴 严重 | 无法主动取消运行中的工作流 | 【已修复】 |
| S5 | 🔴 严重 | resume 存在 TOCTOU 并发竞态 | 【已修复】 |
| S6 | 🔴 严重 | resume 传 None 会从头重跑 | 【已修复】 |
| S7 | 🔴 严重 | 删除 switch/intent 分支后连线残留错位 | 【未修复】 |
| M1-M11 | 🟡 中等 | 健壮性 / 一致性 / 体验类问题（共 11 条） | 【未修复】 |
| L1-L10 | 🔵 轻微 | 代码质量类（共约 10 条） | 【未修复】 |

**总体结论**：单节点测试链路与画布交互质量很高；但**生产化前有 7 个确凿的严重问题**，集中在多用户安全隔离、长任务可恢复性、并发控制。

---

## 一、🔴 严重问题（均经源码确认，建议上线前必修）

### S1 【已修复】工作流实例全量无所有者隔离（IDOR）—— 信息泄露 + 越权控制

> ✅ **已修复（2026-06-23）**：`WorkflowDefinition`/`WorkflowInstance` 增加 `user_id` 字段（自动 CRUD 的 page/list/info 经 DataScope 自动过滤）；`WorkflowService` 重写 `add`/`update`/`delete` 注入 owner 并校验越权；`start`/`resume`/`testNode`/`logs`/`stream` 五个自定义接口接入 `assert_workflow_owner` 校验。覆盖 11 个单测，168 全量测试通过。
> 📌 **提交前审查补充（2026-06-23）**：发现 `WorkflowInstanceService.delete`（自动生成的实例删除接口）此前**未覆盖** owner 校验——仅 `WorkflowService.delete`（定义）与五个自定义接口覆盖了，实例的 CRUD `delete` 漏网，普通用户可越权软删他人实例（含运行中）。本次补 `WorkflowInstanceService.delete` 逐条校验 owner。
> 📌 `start_instance` **不**校验 definition owner：设计上任何用户均可启动已启用的工作流定义、实例归属启动者（`test_start_instance_writes_user_id` 明确此语义），definition 可见性已由 DataScope 在 page/list/info 限制，故不视为越权。

- **严重度**：🔴 严重（安全）
- **位置**：
  - [workflow.py:17-40](../backend/app/modules/workflow/model/workflow.py#L17-L40) — `WorkflowDefinition` / `WorkflowInstance` 继承 `BaseEntity`，只有 `id`/时间戳，**没有 `owner_id` / `create_by` / `department_id`**
  - [instance.py:92-105](../backend/app/modules/workflow/controller/admin/instance.py#L92-L105) — `get_logs` 手写 `select(...).where(instance_id==...)`，无所有者过滤
  - [instance.py:107-138](../backend/app/modules/workflow/controller/admin/instance.py#L107-L138) — `stream_progress` 只校验登录，权限点竟复用 `workflow:instance:page`
  - [instance.py:70-79](../backend/app/modules/workflow/controller/admin/instance.py#L70-L79) — `resume` 任意管理员可对他人 `paused` 实例注入 `user_input`
- **问题**：框架层 `apply_data_scope` 探测到模型缺少 `user_id`/`department_id` 字段时直接 return，`resolve_data_scope` 形同虚设；而这些手写查询接口又完全不走 CRUD 的 DataScope 注入。
- **影响**：管理员 A 拿到自己实例 id=10，遍历 `instanceId=1..N` 调 `/logs`、`/stream`，即可读取他人工作流的完整节点输入/输出（含用户 prompt、PII、模型响应），并对他人挂起的工作流投递恶意输入。
- **修复建议**：
  ```python
  # 1. 模型加字段
  class WorkflowInstance(BaseEntity, table=True):
      owner_id: int | None = Field(default=None, foreign_key="sys_user.id", index=True)

  # 2. start_instance 写入 current_user.id
  # 3. get_logs/stream/resume 内显式校验
  if instance.owner_id != current_user.id and not current_user.is_super_admin:
      raise HTTPException(403, "无权访问该工作流实例")
  ```

### S2 【已修复】PII 落库/SSE 副本脱敏

> ✅ **已修复（2026-06-23）**：新增 `AiSecurityService.mask_sensitive_dict` 递归脱敏，对 `WorkflowExecutionLog.input_data`/`output_data` 与 SSE 推送的 `variables` 副本脱敏（workflow_tasks.py 四处）。
> ⚠️ **对原判断的修正**：`skip_masking=True` 维持不变 —— LLM 节点输出需进入 `variables` 供下游节点计算（如发短信），改 False 会把 PII 脱敏成 `138****5678` 污染下游、破坏功能。真正泄露点是落库/SSE 副本，已对副本脱敏。
> 📌 `state_data` 本轮未脱敏（`workflow_output` 提取依赖原文），待 S3 持久化 checkpointer 落地后降级为纯展示快照再处理。

- **严重度**：🔴 严重（安全/合规）
- **位置**：
  - [workflow_service.py:73](../backend/app/modules/workflow/service/workflow_service.py#L73) — `skip_masking=True` 硬编码，绕过 commit `6a2cb67` 引入的 `AiSecurityService.mask_sensitive_output`
  - [workflow_tasks.py:142-143](../backend/app/modules/workflow/tasks/workflow_tasks.py#L142-L143) — `input_data=json.dumps(current_vars)`、`output_data=json.dumps(new_vars)`，用户提交的手机号/身份证/邮箱被**原样写入** `WorkflowExecutionLog` 并经 `/logs`、`/stream` 回传
- **问题**：两层独立缺陷——`skip_masking=True` 关闭了模型**输出**脱敏；而 `current_vars` 落库这层会让用户**输入**的 PII 无论脱敏开关都泄露。
- **影响**：用户在工作流中提交的 PII 经日志/SSE 长期留存，叠加 S1 的 IDOR 等于全平台 PII 暴露。
- **修复建议**：移除 `skip_masking=True`（或改为按节点配置开关，默认开）；对 `input_data/output_data/state_data` 落库前统一过一遍 `mask_sensitive_output`。

### S3 【已修复】默认 checkpointer 是 MemorySaver —— 多进程/重启后无法恢复

> ✅ **已修复（2026-06-23）**：`WORKFLOW_CHECKPOINT_BACKEND` 默认改 `sqlite`；`checkpointer.py` sqlite 分支改用 `SqliteSaver(conn)` 显式构造 + `setup()` 建表 + WAL/busy_timeout（原 `from_conn_string` 是 `@contextmanager`、返回上下文管理器而非 saver，属潜伏 bug，一并修正）；未知 backend 不再静默 fallback、改为抛 `ValueError`；`startup_checks.py` 新增校验：生产禁用 memory、任意环境未知值报 error。
> 📌 **提交前审查补充（2026-06-23）**：发现 postgres 分支**遗留了同样的 `from_conn_string` 误用**（sqlite 分支修了、postgres 分支没同步）——`PostgresSaver.from_conn_string` 同样是 `@contextmanager`，调用 `.setup()` 会崩，导致一旦配置 `WORKFLOW_CHECKPOINT_BACKEND=postgres`（startup_checks 推荐的生产后端）首次执行工作流即崩溃。本次一并修为显式 `psycopg.Connection.connect(...)` + `PostgresSaver(conn)` + `setup()`，并剥离 `postgresql+psycopg://` 方言后缀（psycopg3 不认 SQLAlchemy 的 `+psycopg`）。

- **严重度**：🔴 严重（可恢复性）
- **位置**：[checkpointer.py:29](../backend/app/modules/workflow/service/checkpointer.py#L29) — 默认 `"memory"`；执行入口 [workflow_tasks.py:71](../backend/app/modules/workflow/tasks/workflow_tasks.py#L71) 用全局单例
- **问题**：Celery 默认 prefork 按 CPU 核数开多个子进程，同一实例的不同节点任务可能落到不同子进程，各自 MemorySaver 互相隔离 → resume 时找不到 `thread_id` → 当成全新执行；Worker 重启后所有 `paused`（等待人工输入）实例变成无法恢复的孤儿。
- **影响**：human_input 的"暂停-恢复"语义在多 Worker 下不可靠。

### S4 【已修复】无法主动取消运行中的工作流 —— 只能等 30 分钟硬超时

> ✅ **已修复（2026-06-23）**：新增 `TERMINAL_STATUSES` 常量 + `cancel_instance`（原子 CAS running/paused→cancelled + `revoke(terminate=True)` 硬杀后背 + 发 `cancelled` 事件）+ `/cancel` 接口；执行主循环改为 `asyncio.wait_for(__anext__, WORKFLOW_NODE_TIMEOUT)` 实现 per-node 超时，并在每节点回查 `instance.status` 协作式退出；三处终态写入（success/failed/paused）改为 CAS，避免覆盖已写入的 cancelled；SSE break 集合加 `cancelled`。复刻 AI 模块 `task_service.cancel` 的成熟范例。

- **严重度**：🔴 严重（可用性 + 成本）
- **位置**：
  - [instance.py](../backend/app/modules/workflow/controller/admin/instance.py) 全文**没有 cancel/abort 接口**
  - [workflow_tasks.py:91-160](../backend/app/modules/workflow/tasks/workflow_tasks.py#L91-L160) — 主循环 `async for event in events` **从不回查 `instance.status`**，也**没有 per-node timeout**
- **影响**：配错的 LLM/图像节点卡住时，用户除等 `task_time_limit=30*60` 硬超时外别无他法，**AI 调用费用照常产生**。

### S5 【已修复】resume 存在 TOCTOU 并发竞态 —— 可重复扣费

> ✅ **已修复（2026-06-23）**：`resume_instance` 的状态迁移改为 DB 原子 CAS `UPDATE ... WHERE id=? AND status='paused'`，`rowcount==0` 返回 409。**选 DB 乐观锁而非 Redis 锁**：`cache_service.get_redis_client()` 在 Redis 不可用时降级为进程内字典（非原子），开发/测试环境 Redis 锁不可靠；DB 级谓词原子性有保证。同一 CAS 模式复用于 S4 的 cancel 状态迁移。

- **严重度**：🔴 严重（并发/数据安全）
- **位置**：[workflow_service.py:1042-1055](../backend/app/modules/workflow/service/workflow_service.py#L1042-L1055)
- **问题**：两个并发 resume 请求都读到 `paused` → 都通过 → 都投递 `execute_workflow.delay` → 两个 Worker 并发跑同一 `thread_id` → checkpointer 写入竞态 + LLM/图像重复扣费。
- **影响**：重复扣费 + 状态竞态。

### S6 【已修复】resume 传 None 会让暂停的工作流从头重跑

> ✅ **已修复（2026-06-23）**：`resume_instance` 开头加 `user_input is None` 守卫（400）；DTO `user_input: Any` 收紧为 `str | dict[str, Any] | list[Any]`（Pydantic 联合类型天然拒 None）+ 64KB 体积上限校验（兼修 L7）。

- **严重度**：🔴 严重（正确性）
- **位置**：[workflow_service.py:1060](../backend/app/modules/workflow/service/workflow_service.py#L1060) + [workflow_tasks.py:39](../backend/app/modules/workflow/tasks/workflow_tasks.py#L39) + [workflow_tasks.py:77](../backend/app/modules/workflow/tasks/workflow_tasks.py#L77) + [workflow.py:138](../backend/app/modules/workflow/model/workflow.py#L138)
- **问题**：`json.dumps(user_input)` 在 `user_input=None` 时得到字符串 `"null"` → `json.loads("null")=None` → `if resume_val is not None` 不成立 → **走 initial_state 分支，从 start 重新执行**，而非从 human_input 恢复。
- **影响**：暂停的工作流被误从头重跑，跳过人工输入节点。

### S7 【未修复】删除 switch 的 Case / intent 的分支后连线残留且标签错位（前端唯一确凿 🔴）

- **严重度**：🔴 严重（正确性）
- **位置**：[switch-config.vue:23](../frontend/src/modules/workflow/components/node-configs/switch-config.vue#L23)
  ```vue
  @click="config.cases.splice(index, 1)"   <!-- 只删 config，不清理边 -->
  ```
  配合 `editor.vue` 的 `getEdgeLabel`（用数组下标解析 `sourceHandle='case_N'`）；后端 [compiler.py:586+](../backend/app/modules/workflow/service/compiler.py#L586) 完全按 sourceHandle 走分支。intent-classifier-config 同型问题。
- **影响**：删中间一项后，`case_2` 这条边被重新解读为**当前** `cases[2]`，标签和运行分支都错位；保存后运行路径与用户预期不符。
- **修复建议**：删 case 时同步删除 `source === nodeId && sourceHandle === 'case_'+index` 的边；或改用稳定 handle id（`case_<uuid>`）并在 config 存 handleId→value 映射。

---

## 二、🟡 中等问题

### M1 【未修复】`validate_graph` 对缺 `id` 的节点抛裸 `KeyError`

- **位置**：[compiler.py:198](../backend/app/modules/workflow/service/compiler.py#L198) — `{n["id"]: n for n in nodes}` 无守卫，与 L200 的 `if "id" in n` 守卫自相矛盾
- **影响**：畸形 JSON（节点缺 id）导致 `KeyError` → Celery 层只写入无意义的 error_message，应给"节点缺少 id 字段"提示
- **修复**：改为 `if "id" in n` 守卫，并在前面显式校验 id/type 必填

### M2 【未修复】校验与编译对 group→controller 推断不一致

- **位置**：[compiler.py:299-305](../backend/app/modules/workflow/service/compiler.py#L299-L305) / [337-343](../backend/app/modules/workflow/service/compiler.py#L337-L343) / [881-896](../backend/app/modules/workflow/service/compiler.py#L881-L896)
- **问题**：三处都从 `loop_body_group.config.controllerNodeId` 推断 controller，但**仅编译阶段有"从边推断"兜底**，校验阶段没有，可能"校验通过但编译崩"
- **修复**：提取公共推断函数三处统一调用；或校验阶段强制要求显式 `controllerNodeId`

### M3 【未修复】`recover_orphaned_instances` 5 分钟窗口误杀长耗时实例

- **位置**：[workflow_service.py:1149](../backend/app/modules/workflow/service/workflow_service.py#L1149) — `timedelta(minutes=5)`
- **影响**：图像节点常 5-10 分钟，部署重启时正常实例被误判 failed，错误信息"Server restarted"误导排查
- **修复**：cutoff 拉到与 `task_time_limit` 一致（30 分钟）或基于 `celery_task_id` + `AsyncResult.state` 探活；改为可配置

### M4 【未修复】异常堆栈 `str(e)` 直接回传前端

- **位置**：[workflow_service.py:78](../backend/app/modules/workflow/service/workflow_service.py#L78) / [1135](../backend/app/modules/workflow/service/workflow_service.py#L1135)、[workflow_tasks.py:192](../backend/app/modules/workflow/tasks/workflow_tasks.py#L192)
- **影响**：泄露 provider 错误、内部字段名、文件路径，辅助攻击
- **修复**：对外只返回通用化错误，详细 `str(e)` 仅写入 `logger.error`

### M5 【未修复】`node-inputs-editor` 的 `nameErrors` 跨节点残留 + 不阻断保存/测试

- **位置**：[node-config-panel.vue:57-61](../frontend/src/modules/workflow/components/node-config-panel.vue#L57-L61)（该组件在 `:key` div **外**，切换节点不重建）；`node-inputs-editor.vue` 的 `nameErrors` 为组件内 reactive
- **影响**：跨节点错误提示污染；非法/空 inputs 仍可持久化与提交测试
- **修复**：`watch(() => props.modelValue, ...)` 清空 `nameErrors`；保存/测试入口阻断非法 inputs

### M6 【未修复】试运行写 `el.class`/`runLog` 触发 deep watch，污染 `isDirty`

- **位置**：`useWorkflowTest.ts:197-235` + `editor.vue` 的 deep watch（约 850-860 行）
- **影响**：试运行中保存按钮误亮、可能保存运行中快照；每次轮询还清空 `_upstreamCache`
- **修复**：watch 内排除运行态字段，或引入 `isRunning` 标志短路；把 `runLog`/`class` 移到独立的 `Map<nodeId, runtimeState>`

### M7 【未修复】`duplicateNode` 复制时未清 `runLog`/`class`，且 group 内节点坐标未转换

- **位置**：`editor.vue:1497-1541`
- **影响**：复制节点显示伪执行结果、边框变色；group 内节点复制后 `parentNode` 被删但坐标仍是相对 group 的，位置漂移
- **修复**：`delete newNode.data.runLog; delete newNode.class;` 若原节点有 parentNode，坐标加上 group.position

### M8 【未修复】`useNodeTest` 无 token 隔离，并发测试串结果

- **位置**：`useNodeTest.ts:51` / `144-146`
- **影响**：节点 A 测试中切到 B 再测试，A 返回时结果被写到 B 节点（用 `nodeTestDialog.nodeId` 查找）
- **修复**：`startNodeTest` 开头 `const token = ++testToken`，异步回来 `if (token !== testToken) return`

### M9 【未修复】`cl-json-tree` 用 `index` 作 `:key`，中间删除字段会错位

- **位置**：`cl-json-tree-editor.vue:16`、`cl-json-tree-node-item.vue:114`
- **影响**：Vue 列表按 index 复用 DOM，删除中间项后输入框内容与数据错位
- **修复**：每个节点分配稳定唯一 id（`crypto.randomUUID()`），`:key="node._uid"`

### M10 【未修复】循环/批处理节点列表长度无上限

- **位置**：[workflow_service.py:451-492](../backend/app/modules/workflow/service/workflow_service.py#L451-L492)（循环）/ [495-533](../backend/app/modules/workflow/service/workflow_service.py#L495-L533)（批处理）
- **影响**：上游 LLM 可返回任意长数组 → "爆炸图"烧 Celery worker + AI 配额；`concurrency_limit` 已限到 ≤20，但列表长度本身无上限
- **修复**：`execute_loop_controller_node` / `execute_batch_processor_node` 入口对 `len(items)` 设硬上限（如 ≤200）

### M11 【未修复】SafeEvaluator 不支持切片、BoolOp 不短路、dict 缺键即抛

- **位置**：[compiler.py:81-86](../backend/app/modules/workflow/service/compiler.py#L81-L86)（BoolOp 列表推导不短路）、[99-103](../backend/app/modules/workflow/service/compiler.py#L99-L103)（Attribute dict 缺键抛 TypeError）、Subscript 未处理 `ast.Slice`
- **影响**：条件表达式写法受限（`a and a.field` 防御性写法失败、`messages[0:3]` 切片失败），错误信息晦涩
- **修复**：BoolOp 改惰性迭代；Attribute dict 缺键返回 None（与 `_deep_get` 对齐）；补 `ast.Slice` 处理

---

## 三、🔵 轻微问题

| 编号 | 状态 | 位置 | 要点 |
|---|---|---|---|
| L1 | 【未修复】 | [compiler.py:536-540](../backend/app/modules/workflow/service/compiler.py#L536-L540) 等 | `node_config[route]=route` 冗余副作用（见下方"误报"说明：不污染执行器，但建议删除） |
| L2 | 【未修复】 | [compiler.py:174-179](../backend/app/modules/workflow/service/compiler.py#L174-L179) | `convert_keys_to_snake` 递归无深度守卫，深层嵌套可触发 RecursionError |
| L3 | 【部分修复】 | [compiler.py:811-823](../backend/app/modules/workflow/service/compiler.py#L811-L823) | `apply_input_mappings`：本轮拦截一处**回归**——空映射被改为返回 `{}`，导致未配输入映射的节点（执行器如 `execute_llm_node` 直接用其渲染 prompt）提示词变量全部丢失，已恢复为 `return global_vars`；原"形状不一致"轻微项保留 |
| L4 | 【未修复】 | `custom-nodes/*.vue` | 所有自定义节点组件普遍缺 `defineOptions({ name })`，影响 keep-alive |
| L5 | 【未修复】 | [compiler.py:160](../backend/app/modules/workflow/service/compiler.py#L160) | `render_template` 正则会吞掉模板里的 JSON 片段（`{"a":1}` 被当变量路径） |
| L6 | 【未修复】 | [workflow_service.py:573-597](../backend/app/modules/workflow/service/workflow_service.py#L573-L597) | 图像节点失败静默返回空字符串，UI 无感知 |
| L7 | 【未修复】 | [workflow.py:134-138](../backend/app/modules/workflow/model/workflow.py#L134-L138) | `WorkflowInstanceResumeRequest.user_input: Any` 绕过 Pydantic 校验 |
| L8 | 【未修复】 | 限流中间件 IP 维度 | `/testNode`、`/start`、`/resume` 高成本接口仅享 IP 维度限流，建议加 per-user |
| L9 | 【未修复】 | `useUndoRedo.ts:32-36` | pushSnapshot 满历史时 shift 但 pointer 不更新（不崩溃，但代码异味，建议简化） |
| L10 | 【已修复】 | `workflow_service.py` + `event_bus.py` | `workflow_event_listeners` 死代码已删除；`event_bus.py` 的 import/遍历引用一并移除（此前 `workflow_service.py` 删定义后 `event_bus.py` 仍 `import` 它，导致所有 `cancel` 触发 `ImportError` 的预存回归——本次拦截修复） |

---

## 四、审查中被否决的误报（记录验证严谨性）

| 原始报告 | 判定 | 原因 |
|---|---|---|
| 🔴 compiler `_add_conditional_edges_for_node` 把路由值写回 config 会覆盖节点配置 | **误报** | [`convert_keys_to_snake`](../backend/app/modules/workflow/service/compiler.py#L174-L179) 返回**新 dict**，`node_config` 是局部变量；`create_node_runner` 用的是另一次独立调用。写入只影响 router 闭包，不污染执行器 config。仅属冗余代码（已记为 L1）。 |
| 🔴 `useUndoRedo.pushSnapshot` 历史满 50 后指针错位导致 undo 崩溃 | **误报** | 数学验证：push 前 `pointer ≤ length-1`，push 后 length+1，即使 shift 回 50，`pointer ≤ 49 = length-1` 恒成立，`history[pointer]` 永远有效。逻辑不优雅但**不会崩溃**（已记为 L9）。 |

---

## 五、已核对健康的点（覆盖面确认）

- **提示词注入检测未被绕过**：LLM 节点经 `AiModelRuntimeService.chat`，`check_input_safety` 对非 system 消息执行注入正则 + 长度限制，工作流同样受保护
- **`safe_eval` AST 沙箱未发现逃逸**：白名单节点遍历，未暴露 `eval`/`__import__`/属性链
- **鉴权框架层覆盖完整**：所有写接口挂了 `permission="workflow:..."`，无裸接口（但权限点不等于行级隔离，见 S1）
- **逻辑正确**：循环体 `deepcopy` + 链式状态累积、`batch_processor` 的 Semaphore 并发控制、`_merge_dicts`/`_last_writer_wins` reducer、DFS 环检测、孤立节点检测
- **实现正确**：`test_node` 的 Redis 防重放（`SET NX EX 2`）、配置面板 `:key` 强制重建防串数据、`source=[nodeId,varKey]` 与后端 schema 对齐
- **生命周期清理**：`editor.vue` 的 `onBeforeUnmount` 正确移除键盘监听与 polling；`node-config-panel.vue` 清理 resize 监听

---

## 六、修复优先级路线图

```
第一优先（安全，上生产前必做）   S1 IDOR + S2 PII 落库
第二优先（可恢复性/成本）        S3 持久化 checkpointer + S4 取消能力 + S5 并发锁
第三优先（正确性）              S6 resume None + S7 删 case 残留边 + M1 KeyError
第四优先（健壮性/体验）          M3-M11 逐步收敛
```

S1+S2 是**多用户场景下的信息泄露**，风险最高且修复成本最低（加字段 + 校验），建议最先做。S3+S4+S5 决定工作流能否真正上生产。

---

## 七、关联问题（测试基础设施，超出 workflow 模块本身）

> 本节归档在 workflow 安全审查 + PG 迁移过程中发现的测试基础设施问题。虽不属于 workflow 模块代码缺陷，但影响"在真实 PG 上跑测试"的安全性，故记录于此。

### T1 【未修复】集成测试通过 TestClient(app) 读写真实 PG 业务数据

- **严重度**：🟡 中等（测试隔离 / 数据污染）
- **位置**：[test_framework_alignment.py:214-332](../backend/tests/test_framework_alignment.py#L214-L332) — `test_crud_page_and_list_support_get_and_post`、`test_admin_crud_requires_authentication_and_permission`、`test_eps_uses_public_prop_and_source_field` 三个集成测试
- **问题**：这三个测试通过 `TestClient(app)` 触发应用 lifespan，在真实 `app_engine`（PG）上执行 `init_db()` 的 `create_all`，并直接读写业务表。其中 `test_admin_crud_requires_authentication_and_permission` 会向 `sys_user` 插入 `limited_*` 临时用户（[test_framework_alignment.py:235-247](../backend/tests/test_framework_alignment.py#L235-L247)），且无 teardown 清理。
- **影响**：
  - 在生产/共享 PG 上跑测试会污染业务数据（残留测试用户、可能触发唯一约束/外键问题）
  - 测试与真实 DB schema 强耦合，迁移期脆弱
- **与本次修复的关系**：2026-06-23 已修复根因之一——"夹具表 `table=True` 模型污染全局 metadata 被带建到生产库"（`ScopedRow`/`PlainRow`/`TxRow` 经 `MetaData.remove` 摘除）。但**集成测试直接读写业务表**这一层未处理，超出"夹具表污染"范围，未强行重构以免扩大改动面。
- **修复建议**：
  - **方案 A（推荐）**：集成测试指向独立测试库（`TEST_DATABASE_URL`），fixture 负责 init + 跑完 teardown
  - **方案 B**：保留真实库但用事务回滚 fixture（`SAVEPOINT` 包裹，测试结束 rollback），至少补齐 `limited_*` 用户清理
  - 配套：CI 与本地使用独立 DB，杜绝触碰开发/生产库

---

## 变更记录

| 日期 | 操作 | 说明 |
|---|---|---|
| 2026-06-22 | 创建 | 初次审查，记录 7 严重 + 11 中等 + 10 轻微，2 误报已剔除 |
| 2026-06-23 | 修复 S1/S2 | S1：user_id 隔离 + DataScope + 5 接口 owner 校验；S2：mask_sensitive_dict 落库/SSE 副本脱敏（修正 skip_masking 判断）。168 测试全过 |
| 2026-06-23 | 修复 S3/S4/S5/S6 | S3：checkpointer 默认 sqlite + 修 from_conn_string 潜伏 bug + 启动校验；S4：cancel_instance + /cancel + per-node 超时 + 协作式取消 + 终态 CAS；S5：resume DB 原子 CAS（弃 Redis 锁）；S6：None 守卫 + DTO 收紧（兼修 L7）。新增 19 测试，ruff 全绿 |
| 2026-06-23 | 记录 T1 | 记录测试基础设施问题：集成测试经 `TestClient(app)` 读写真实 PG 业务数据（夹具表污染根因已修，业务表读写层未处理，待后续） |
| 2026-06-23 | 提交前审查修复 | S1 补 `WorkflowInstanceService.delete` owner 校验（实例删除越权遗漏）；S3 postgres 分支 `from_conn_string` 误用修复（显式 Connection + setup）；L3 恢复 `apply_input_mappings` 空映射返回 `global_vars`（修复提示词变量丢失回归）；L10 删 `workflow_event_listeners` 死代码并修 `event_bus.py` ImportError（cancel 崩溃预存回归）。46 相关测试通过 |
