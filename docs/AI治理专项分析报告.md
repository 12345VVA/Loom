# Loom 项目 AI 治理专项分析报告

> 🔄 **治理结论已被部分取代**：2026-10-04 的 [架构与治理评审](./架构与治理评审-2026-10-04.md) 已就治理维度重新评级并给出 H/M/L 编号清单与处理记录。本报告（2026-07-30）保留作 10 维度深度专报，**治理结论与优先级以 10-04 版为准**。

## 概览

本报告系统性梳理 Loom 项目（Vue 3 + FastAPI + Celery 全栈 AI 内容生成平台）的 AI 治理能力现状，作为团队内部审计与合规基线，定位运行期与编排期的治理盲点，并给出可落地的改进建议。

- **报告目的**：建立 Loom 项目 AI 治理能力基线，支撑后续审计、合规检查与迭代规划。
- **覆盖范围**：后端 `backend/app/modules/ai`、`backend/app/modules/workflow`、`backend/app/modules/workflow_eval`、`backend/app/framework/middleware`、`backend/app/core`、`backend/app/celery_app.py`，以及前端 `frontend/src/modules/ai`、配置层 `.env.example`、`backend/app/modules/ai/config.py`、`docker-compose.yml`。
- **读者对象**：Loom 团队维护者、内部审计方、安全合规评审人员。
- **写作基线**：所有描述基于代码事实，引用具体文件路径、函数名、配置项或常量名，不使用主观褒贬词汇。

## 治理能力总览

Loom 的 AI 治理围绕 **三表模型** 与 **四维配额矩阵** 构建：

**三表模型**（`backend/app/modules/ai/model/ai.py`）：

| 实体 | 角色 | 关键字段 |
|------|------|----------|
| `AiGovernanceRule` | 治理规则定义 | max_requests / max_tokens / max_cost_micro_usd / max_concurrent、period、scope_type、mode |
| `AiGovernanceEvent` | 治理事件流水 | event_type（allowed/blocked/warn/breach）、metric、rule_id、window 起止 |
| `AiRuntimeInvocation` | 运行期调用生命周期 | invocation_id、status、started_at/finished_at、task_id、cc_keys |

**四维配额矩阵**：

- **指标维度**：`request` / `token` / `cost` / `concurrent`
- **周期维度**：`minute` / `day` / `month`（`AI_GOVERNANCE_PERIODS`，model/ai.py:33）
- **范围维度**：`global` / `user` / `profile`（`AI_GOVERNANCE_SCOPE_TYPES`，model/ai.py:32）
- **模式维度**：`enforce`（拦截）/ `observe`（仅观测告警）（`AI_GOVERNANCE_MODES`，model/ai.py:34）

三阶段检查流程：预检（`_check_pre_rule`）→ 并发检查（`_acquire_concurrent`）→ 后置事件（`_record_post_events`），由 `AiGovernanceService` 在 `AiModelRuntimeService._invoke` / `_stream_invoke` 中统一编排。

## 分析维度说明

本报告从 10 个维度评估 AI 治理能力：

1. **AI 模型管理**：模型抽象、适配器、Fallback 链、运行时入口
2. **AI 安全与权限**：调用权限点、scope 鉴权、限流、CSRF、Token 版本
3. **数据安全**：Prompt 注入检测、PII 脱敏、密钥加密、上传白名单
4. **审计与可观测性**：调用日志、治理事件、Runtime invocation、结构化日志、链路追踪
5. **伦理与合规**：SafetyEvaluator、评估器、内容安全、偏见控制
6. **成本与资源治理**：配额规则、并发计数、成本精度、看板、清理任务
7. **Celery 异步任务治理**：队列路由、可靠性三件套、超时、重试、定时任务
8. **AI 工作流编排**：AST 沙箱、循环检测、节点重试、检查点、SSE
9. **前端 AI 模块**：治理规则/事件/日志/看板 CRUD、权限点、国际化
10. **配置层面治理**：模块配置、生产强制开关、密钥、限流、上传、会话、日志

---

## 维度 1：AI 模型管理

### 实现位置

- `backend/app/modules/ai/model/ai.py` — AI 全部实体与 DTO（`AiProvider`/`AiModel`/`AiModelProfile`/`AiModelCallLog` 等）
- `backend/app/modules/ai/service/registry_service.py` — `AiModelRegistryService.resolve`
- `backend/app/modules/ai/service/provider_service.py` — Provider 同步与密钥管理
- `backend/app/modules/ai/service/profile_service.py` — Profile CRUD 与 Fallback 链
- `backend/app/modules/ai/service/runtime_service.py` — `AiModelRuntimeService` 统一运行时
- `backend/app/modules/ai/service/adapters/` — `openai_http.py` / `openai_compatible.py` / `claude.py` / `gemini.py` / `ollama.py` / `factory.py`
- `backend/app/modules/ai/controller/admin/{provider,model,profile}.py` — Admin scope CRUD
- `backend/app/modules/ai/controller/aiapi/model.py` — AI 调用入口（`aiapi` scope）

### 治理现状

**三层模型抽象**：`AiProvider`（厂商）→ `AiModel`（模型）→ `AiModelProfile`（调用配置）。Profile 挂载 `temperature` / `top_p` / `max_tokens` / `timeout` / `retry_count` / `response_format` / `tools_config` 等运行参数。

**12 种适配器**：`AI_ADAPTERS = {openai-compatible, ollama, gemini, claude, deepseek, volcengine-ark, bailian, hunyuan, qianfan, zhipu, minimax, mimo}`（model/ai.py:17-30）。

**6 种模型类型**：`AI_MODEL_TYPES = {chat, embedding, image, audio, video, rerank}`（model/ai.py:31）。

**Fallback 链治理**：

- `AiModelProfile.fallback_profile_id` 声明降级链。
- 保存期环检测：`_ensure_fallback_acyclic`（profile_service.py:132）。
- 运行期同步防环：`_fallback_chain_has_cycle`（runtime_service.py:638）。
- 深度限制：`MAX_FALLBACK_DEPTH=5`，通过 `contextvars.ContextVar` 跨异步边界计深。

**Profile 解析**：`registry_service.resolve` 优先按 `profile_code` 精确匹配，否则按 `scenario + is_default + is_active` 兜底。

**统一运行时入口**：`AiModelRuntimeService` 暴露 `chat` / `stream_chat` / `embedding` / `image` / `rerank` / `audio` / `video` 七个方法，统一走 `_invoke` / `_stream_invoke` 编排"治理 → 适配器 → 日志 → 脱敏"链路。

**状态隔离**：Admin scope 仅做 CRUD；AI 调用走独立 `aiapi` scope；`AiRuntimeController` 用 `_NoopService` 占位，防止误用 CRUD 通道调用模型。

**Provider 同步模型默认禁用**：`sync_models` 创建的模型 `is_active=False`，capabilities 标注 `manual-classification-required`（provider_service.py:107-118），强制人工分类后才能启用。

### 缺口/风险

- **重试无 jitter**：`_invoke_with_retry`（runtime_service.py:368）按 `retry_delay_seconds` 固定间隔重试，高并发下多请求同步重试会形成重试风暴。
- **同步生图走线程池**：`/aiapi/ai/model/image` 用 `run_in_threadpool` 包同步管道（controller/aiapi/model.py:106-141），依赖 `ASYNC_THREAD_POOL_SIZE=100`，大流量下可能挤满 anyio 线程池，影响其他异步任务调度。

---

## 维度 2：AI 安全与权限

### 实现位置

- `backend/app/framework/middleware/scope_authority.py` — `AdminAuthorityMiddleware` / `AppAuthorityMiddleware` / `AiApiAuthorityMiddleware`
- `backend/app/modules/ai/controller/aiapi/model.py:40-50` — `require_ai_call_permission`
- `backend/app/modules/base/service/authority_service.py` — 权限校验服务
- `backend/app/framework/middleware/rate_limit.py` — 全局限流中间件
- `backend/app/framework/middleware/admin_csrf.py` + `config.py:_enforce_production_csrf` — CSRF Origin 校验

### 治理现状

**AI 调用专用权限点**：`AI_INVOKE_PERMISSION = "ai:model:invoke"`（aiapi/model.py:37），通过 `require_ai_call_permission` Depends 强制校验，超级管理员旁路。

**三层 scope 鉴权**：`ScopeAuthorityMiddleware` 按 scope（admin/app/aiapi）拆分，`authorize_request` 同步 DB 校验 offload 到线程池，避免阻塞事件循环。

**全局限流分级**（config.py:113-118）：

- `RATE_LIMIT_ADMIN=60`
- `RATE_LIMIT_OPEN=30`
- `RATE_LIMIT_DEFAULT=120`
- `RATE_LIMIT_WHITELIST_PATHS=/docs,/redoc,/openapi.json,/health`

`aiapi` 走 default 限。

**限流粒度**：client_id 优先用 `Bearer token` 的 MD5 哈希，无 token 回退到 IP（rate_limit.py:69-76），Redis 原子计数，固定窗口 60 秒。

**限流 fail-open 策略**：Redis 故障时记录警告后放行（rate_limit.py:98-103）。

**生产强制 CSRF**：`_enforce_production_csrf`（config.py:177-185）在 `DEBUG=False` 时强制开启 `ADMIN_CSRF_ORIGIN_CHECK_ENABLED`，忽略 .env 关闭设置。

**Token 版本号机制**：`increment_user_token_version` 一键使所有旧 Token 失效，Redis 原子 INCR + 30 天 TTL，Redis 不可用时降级进程内缓存。

**可信代理链**：`TRUSTED_PROXIES` 从右向左跳过可信代理，取第一个非可信 IP，防 X-Forwarded-For 伪造。

**登录防爆破**：

- `BASE_LOGIN_ACCOUNT_FAIL_MAX=5`
- `BASE_LOGIN_IP_FAIL_MAX=20`
- `BASE_LOGIN_LOCK_TIME=15 分钟`
- 验证码滑块轨迹校验

### 缺口/风险

- **`aiapi` 限流与 admin 同级**：AI 调用走 `RATE_LIMIT_DEFAULT=120/分钟`，对 LLM 调用过于宽松，单用户每分钟可发起 120 次 LLM 请求，叠加 token 成本风险高。
- **限流 fail-open vs 治理 fail-closed 不一致**：全局限流 Redis 故障时放行，但 `AiGovernanceService` 对 cost 类并发规则 fail-closed（governance_service.py:366-376），两套机制在 Redis 故障下行为分裂。
- **`TASK_ALLOWED_SERVICES` 留空时允许所有已扫描 service 的公开方法**（config.py:127-130），当前默认配置实际是放行的，TaskInvoker 白名单未起到收紧作用。

---

## 维度 3：数据安全

### 实现位置

- `backend/app/modules/ai/service/security_service.py` — Prompt 注入检测 + PII 脱敏
- `backend/app/framework/middleware/operation_log.py` — `SENSITIVE_FIELDS` / `mask_sensitive_data`
- `backend/app/core/secret.py` — `encrypt_secret` / `decrypt_secret` / `mask_secret`
- `backend/app/modules/ai/service/utils.py:sanitize_options_for_log` — AI 调用日志选项脱敏
- `config.py:UPLOAD_MAX_SIZE_MB` / `UPLOAD_ALLOWED_EXTENSIONS` — 上传白名单

### 治理现状

**Prompt 注入字典**：`INJECTION_PATTERNS`（security_service.py:20-30）9 条中英文越狱/注入模式，正则编译为 `INJECTION_REGEX`，在 `check_input_safety` 中对每条消息检测。

**多模态注入检测**：对 list 形式 content 提取所有 text 部分拼接后检测（security_service.py:57-66）。

**System 消息不跳过**：明确注释不得对 system 角色做跳过处理（security_service.py:50-53），防 role 字段伪造绕过检测。

**DoS 长度拦截**：`MAX_INPUT_LENGTH=20000` 字符，超限返回 400。

**PII 脱敏三种类型**：

- 手机号：保留前 3 后 4，如 `138****5678`
- 身份证：保留前 6 后 4
- 邮箱：用户名中间打码

`mask_sensitive_dict` 递归处理 dict/list 结构。

**流式脱敏策略**：流式 delta 阶段不脱敏，仅在 `done` 事件中对完整内容做全量脱敏（runtime_service.py:486-488）。

**结构化数据跳过脱敏**：JSON schema/object 响应不脱敏（runtime_service.py:296-302）。

**`skip_masking` 字段**：`AiChatRequest.skip_masking` 可显式跳过脱敏，工作流内部调用设 `skip_masking=True`（workflow_service.py:73）。

**密钥加密**：Fernet 对称加密（`v2` 版本），兼容旧 `v1` 版本；`api_key_cipher` 字段持久化密文，`api_key_mask` 字段展示掩码；API 响应通过 `_with_secret_flags`（provider_service.py:193）剥除 `api_key_cipher` 并暴露 `hasApiKey` 布尔。

**密钥派生兜底**：`_derive_key` 优先用 `SECRET_ENCRYPTION_KEY`，缺失时回退到 `JWT_SECRET_KEY`（secret.py:56-58）。

**操作日志脱敏**：`SENSITIVE_FIELDS` 集合含 25 个敏感字段名，`mask_sensitive_data` 递归脱敏。

**AI 调用日志选项脱敏**：`sanitize_options_for_log`（utils.py:163）对 `api_key/apikey/authorization` 替换为 `***`，对 `b64_json/image/image_data` 替换为长度+预览摘要，字符串超 500 字符截断。

**上传白名单**：`UPLOAD_ALLOWED_EXTENSIONS` 默认不含 `.svg`（防存储型 XSS）。

**图片远程下载白名单**：`MEDIA_REMOTE_ALLOWED_HOSTS="*.volces.com"`，防 SSRF。

### 缺口/风险

- **Prompt 注入字典偏简单**：仅 9 条正则，无法覆盖变形写法（Unicode 同形字、零宽字符、Base64 编码、多语言变体），无 LLM-based 二次检测，无图像/音频 prompt 注入检测。
- **PII 脱敏类型有限**：仅手机/身份证/邮箱三种，缺银行卡、护照、地址、IP 等。
- **`SECRET_ENCRYPTION_KEY` 可空**：`SECRET_ENCRYPTION_KEY: str = ""`（config.py:70），空时回退到 `JWT_SECRET_KEY`，若两者都泄露则密钥可解。
- **流式阶段不脱敏**：流式 delta 实时输出未脱敏，PII 会先到达客户端，客户端若缓存 delta 会保留原始 PII，后续 `done` 事件的全量脱敏无法回收已发送内容。
- **`skip_masking` 暴露**：`AiChatRequest.skip_masking` 是请求体字段，持有 `ai:model:invoke` 权限的用户可任意开启，绕过 PII 脱敏。

---

## 维度 4：审计与可观测性

### 实现位置

- `backend/app/modules/ai/model/ai.py:AiModelCallLog` — AI 调用日志实体
- `backend/app/modules/ai/service/log_service.py` — 日志写入服务
- `AiGovernanceEvent` + `backend/app/modules/ai/service/governance_service.py:AiGovernanceEventService` — 治理事件
- `AiRuntimeInvocation` — 运行期调用生命周期
- `backend/app/modules/ai/service/stats_service.py:AiModelCallStatsService` — 看板统计
- `backend/app/framework/middleware/operation_log.py` — 操作日志中间件
- `backend/app/core/logging.py` — `JsonFormatter` / `ConsoleFormatter`
- `request_id_ctx` / `current_user_id_ctx` / `workflow_instance_id_ctx` — contextvar 链路追踪
- `backend/app/framework/middleware/metrics.py:record_metric_event` — 指标埋点

### 治理现状

**AI 调用日志全量记录**：`AiModelCallLog` 字段含 provider_id / model_id / profile_id / user_id / scenario / model_type / status / latency_ms / prompt_tokens / completion_tokens / total_tokens / cost_micro_usd / currency / error_message / request_id / workflow_instance_id，17 个字段全部建索引，每次 `_invoke` / `_stream_invoke` 成功/失败/拦截/不支持都写一条。

**5 种调用状态**：`success` / `error` / `blocked` / `unavailable` / `unsupported`；治理拦截记 `blocked`，Redis 故障记 `unavailable`，能力不支持记 `unsupported`。

**治理事件 4 类型**：`allowed` / `blocked` / `warn` / `breach`（model/ai.py:35）；`AiGovernanceEventService.stats` 按事件类型和指标（request/concurrent/token/cost）双维度聚合统计（governance_service.py:143-159）。

**Runtime invocation 全生命周期**：`AiRuntimeInvocation` 记录 invocation_id / user_id / profile_id / model_id / provider_id / status / started_at / finished_at / task_id / cc_keys，从 begin → finish / block 全状态流转；`cc_keys` 持久化便于 worker 重启 / cancel 后精确释放并发计数。

**结构化 JSON 日志**：`JsonFormatter` 输出 `{level, logger, message, time, request_id, path, method, user_id, exception, ...extra}`；文件按天滚动保留 30 天（`LOG_RETENTION_DAYS=30`）；`error.log` 单独过滤 ERROR 级别。

**contextvar 链路追踪**：`request_id_ctx` / `current_user_id_ctx` / `workflow_instance_id_ctx` 跨异步边界传递；`workflow_instance_id_ctx` 让 AI 调用日志可按工作流实例精确聚合 token/cost。

**控制台 traceback 过滤**：`_FRAME_FILTER_SUBSTRINGS` 过滤 starlette / anyio / uvicorn 框架内部帧（logging.py:76-89）。

**看板缓存 + 主动失效**：`STATS_CACHE = CacheNamespace("ai:stats", default_ttl_seconds=90)`，新调用日志写入后 `invalidate_summary_cache()` 主动失效（stats_service.py:21-23、cleanup_service.py:38-40）。

**操作日志异步写入**：`OperationLogMiddleware` 仅记录 `/admin` 前缀的 POST/PUT/DELETE，排除 `/login/upload/eps`，Body 超 1MB 跳过，异步 `asyncio.create_task` 写入。

**指标埋点**：`record_metric_event("rate_limited", path=path)` 在限流触发时记录，`METRICS_ENABLED` 控制是否启用。

### 缺口/风险

- **AI 调用日志不记 prompt 内容**：`AiModelCallLog` 只记 token 数和 request_id，不存原始 prompt 和 response 内容，排查问题只能靠 `summarize_prompt` 在日志文件中留 240 字符预览。
- **治理事件 14 天默认窗口**：`AiGovernanceStatsRequest.days=14`，长期趋势分析需手动调 days。
- **指标后端未明确**：`metrics.py` 的 `record_metric_event` 实现未对接 Prometheus/StatsD，`METRICS_ENABLED=False` 默认关闭。
- **错误日志可能含敏感信息**：`logger.warning(f"AI 调用被拦截: 疑似提示词注入攻击. Content Snippet: {content[:100]}")`（security_service.py:81）直接把用户输入前 100 字符写入日志，未做脱敏处理。

---

## 维度 5：伦理与合规

### 实现位置

- `backend/app/modules/workflow_eval/service/evaluator/safety.py` — `SafetyEvaluator`
- `backend/app/modules/ai/service/security_service.py:check_input_safety` — 运行期输入安全检测
- `backend/app/modules/workflow_eval/` — 整个评估模块
- `backend/app/modules/workflow_eval/service/evaluator/llm_judge.py` — LLM Judge 评估器
- `backend/app/modules/workflow_eval/service/eval_orchestrator.py` / `regression.py` — 评估编排与回归对比

### 治理现状

**SafetyEvaluator 评估器**：`workflow_eval` 模块的 `SafetyEvaluator` 配合红队测试集使用，检查输出 PII 泄露（phone/id_card/email）、自定义敏感正则、期望拒绝时检测拒绝词。

**拒绝词字典**：`_REFUSAL_RE = re.compile(r"(拒绝|不能|无法|抱歉|我不会|不建议|违反|不当|敏感)")`（safety.py:23），8 个中文拒绝词。

**评估三类指标**：`workflow_eval` 含 `rule_match` / `json_schema` / `llm_judge` / `safety` / `composite` 五种评估器，支持批量评估、回归对比、bootstrap 重采样显著性检验（`WORKFLOW_EVAL_BOOTSTRAP_SAMPLES=1000`）。

**LLM Judge 兜底模型**：`WORKFLOW_EVAL_JUDGE_PROFILE` 配置 llm_judge 兜底模型 Profile。

**回归退化阈值**：`WORKFLOW_EVAL_REGRESSION_THRESHOLD=0.1`，单 case score 变化超此值视为退化/改善。

**Prompt 注入拦截**：见维度 3，9 条注入模式 + DoS 长度限制。

### 缺口/风险

- **无输出有害内容检测**：`SafetyEvaluator` 只检测 PII 泄露和拒绝词，不检测仇恨/暴力/色情/自残/儿童不良等内容，未对接专业内容安全 API（OpenAI Moderation、阿里云内容安全）。
- **无模型偏见控制**：未看到任何对模型偏见的检测/缓解机制，无 demographic bias 评估。
- **无使用政策显式声明**：无 Usage Policy / Acceptable Use Policy 配置项。
- **拒绝词字典偏中文**：8 个拒绝词仅中文，英文场景无法覆盖。
- **无审计追溯链**：治理事件有记录，但无端到端的"用户 → 输入 → 模型 → 输出 → 评估"完整审计链。
- **SafetyEvaluator 是评估期工具，非运行期拦截**：运行期 AI 调用不做输出内容安全检测，仅在离线评估阶段使用。

---

## 维度 6：成本与资源治理

### 实现位置

- `backend/app/modules/ai/model/ai.py:AiGovernanceRule` / `AiGovernanceRuleCreateRequest`
- `backend/app/modules/ai/service/governance_service.py:AiGovernanceService`
- `backend/app/modules/ai/service/utils.py:_calculate_cost_micro_usd`
- `backend/app/modules/ai/service/stats_service.py` — 看板统计
- `backend/app/modules/ai/controller/admin/dashboard.py` — 看板控制器
- `backend/app/modules/ai/service/cleanup_service.py` — 治理数据清理

### 治理现状

**四维配额**：`AiGovernanceRule` 支持 `max_requests` / `max_tokens` / `max_cost_micro_usd` / `max_concurrent`。

**三档周期**：`AI_GOVERNANCE_PERIODS = {minute, day, month}`（model/ai.py:33），`_window_bounds`（utils.py:120）按周期计算窗口起止。

**三种范围**：`AI_GOVERNANCE_SCOPE_TYPES = {global, user, profile}`（model/ai.py:32），`_validate_scope` 校验 user/profile 范围必填对应 id。

**双模式**：`AI_GOVERNANCE_MODES = {enforce, observe}`（model/ai.py:34），enforce 拦截（抛 `AiGovernanceBlocked` → 429），observe 仅观测告警不拦截。

**三阶段检查**：

| 阶段 | 函数 | 行为 |
|------|------|------|
| 预检 | `_check_pre_rule`（governance_service.py:453） | request/token/cost 在调用前 SQL 窗口聚合检查；token/cost 在 `current >= limit` 时拦截（block_at_limit=True），request 在 `current > limit` 时拦截 |
| 并发检查 | `_acquire_concurrent` | Redis 原子 `cache_incr` 预占，超限 `cache_decr` 回滚；enforce 抛 `AiGovernanceBlocked`，observe fail-open |
| 后置事件 | `_record_post_events` | 成功后基于实际 usage 和 cost 二次检查，超限记 `breach` 事件 |

**并发计数 fail-closed**：cost 类规则在 Redis 故障时 `AiGovernanceUnavailable` → HTTP 503，避免不可靠计数下放行（governance_service.py:366-376）；monitor 模式 fail-open。

**并发计数持久化**：`AiRuntimeInvocation.cc_keys` JSON 持久化 acquire 的 Redis key，worker 被 terminate 后 `release_for_generation_task` 可按 task_id 精确 decr（governance_service.py:317-340）。

**僵尸计数 TTL**：`_CONCURRENT_TTL = 7200`（2 小时）。

**事件去重通知**：`_notify_once` 通过 `(rule_id, metric, event_type, window_start, window_end, notified=True)` 唯一约束，同一窗口同一事件只通知一次，通知走 `NotificationService.send_business` 推送给所有管理员。

**成本微美元精度**：`cost_micro_usd` 用整数微美元存储，避免浮点误差；`_calculate_cost_micro_usd`（utils.py:136）按 `pricing_config` 的 `input_per_1m` / `output_per_1m` 计算。

**看板多维聚合**：`AiModelCallStatsService.summary` 支持 `group_by=day/user/profile/model`，返回 total/success/error/successRate/avgLatencyMs/totalTokens/costUsd + groups 列表。

**治理数据清理**：Celery beat 每天凌晨 3 点跑 `ai.clean_expired_governance_data`（celery_app.py:86-89），按 `aiTaskPayloadKeepDays=90` / `aiCallLogKeepDays=180` / `aiGovernanceEventKeepDays=180` 清理，参数走 `SysParamService` 可动态调整。

### 缺口/风险

- **预算告警阈值不可配**：规则只有硬上限，无"达到 80% 预警、100% 拦截"分级。
- **成本计价依赖手动维护**：`AiModel.pricing_config` 需管理员手动填写，无自动同步厂商最新价格。
- **observe 模式无自动升级**：observe 模式仅告警，不会因持续触发自动升级为 enforce。
- **预检 SQL 性能**：每次 AI 调用前 `_request_count` / `_token_sum` / `_cost_sum` 跑 3 条 SQL 聚合，高 QPS 下可能成为瓶颈。
- **Token 配额按 sum 累计，不含当前调用**：`_check_pre_rule` 中 token/cost 用 `current >= limit` 拦截，但实际本次调用 token 数未知，可能本次调用远超剩余配额，后置 `_record_post_events` 才记 breach，但调用已经发生并扣费。

---

## 维度 7：Celery 异步任务治理

### 实现位置

- `backend/app/celery_app.py`
- `backend/app/modules/ai/tasks/generation_tasks.py`
- `backend/app/modules/ai/service/task_service.py`
- `backend/app/modules/workflow/tasks/workflow_tasks.py`
- `backend/app/modules/workflow_eval/tasks/eval_tasks.py`

### 治理现状

**6 个 AI 专用队列**：`AI_TASK_QUEUES = (ai.chat, ai.image, ai.embedding, ai.rerank, ai.audio, ai.video)`（celery_app.py:13）。

**task_routes 显式路由**（celery_app.py:60-71）：

- `ai.execute_generation_task → ai.chat`
- `ai.clean_expired_governance_data → default`
- `workflow.execute → workflow`
- `workflow.eval.run → workflow.eval`

**任务可靠性三件套**：

- `task_acks_late=True`：任务执行完成后才 ACK，worker 进程级死亡/OOM kill 时任务会被重新投递。
- `task_reject_on_worker_lost=True`：worker 异常退出时拒绝消息重回队列。
- **CAS 抢占**（generation_tasks.py:42-52）：`UPDATE AiGenerationTask SET status='running' WHERE id=? AND status='pending'`，并发重试或重复入队时仅一个 worker 抢占成功。

**超时双层**：

- `task_time_limit=30*60`（硬超时 30 分钟）
- `task_soft_time_limit=25*60`（软超时 25 分钟，触发 `SoftTimeLimitExceeded` 让任务优雅收尾）

**任务级重试与节点级重试分离**：

- 节点级（工作流）：`WORKFLOW_NODE_RETRY_MAX_ATTEMPTS=1`、`WORKFLOW_NODE_RETRY_BACKOFF_BASE=2.0`，指数退避（compiler.py:1042-1067）
- Profile 级：`AiModelProfile.retry_count` / `retry_delay_seconds`，`_invoke_with_retry` 按固定间隔重试（runtime_service.py:368-389）

**治理并发释放兜底**：`AiGenerationTaskService.cancel` 和 `retry` 都调用 `AiGovernanceService.release_for_generation_task`（task_service.py:70、97）。

**定时任务**：

| 频率 | 任务 |
|------|------|
| 每分钟 | 扫描到期任务（`dispatch-due-system-tasks`） |
| 每天凌晨 2 点 | 清理过期日志（`clean-expired-logs-daily`） |
| 每天凌晨 3 点 | 清理过期 AI 治理数据（`clean-expired-ai-governance-data-daily`） |
| 每 15 分钟 | 巡检超时未终结的评估运行（`sweep-timed-out-eval-runs`） |
| 每天凌晨 4 点 | 清理过期归档工作流版本（`sweep-archived-versions`） |

**工作流节点级超时**：`WORKFLOW_NODE_TEST_TIMEOUT=180`、`WORKFLOW_NODE_TIMEOUT=600`。

### 缺口/风险

- **AI 队列无并发限制**：celery_app.py 未设 `task_annotations` 或 worker `--concurrency` 限制，需在部署层用 `-Q ai.chat -c 4` 控制。
- **任务级重试未启用**：`execute_ai_generation_task` 未配 `autoretry_for` / `max_retries`，worker 失败后不会自动重试，需用户手动点 retry。
- **`task_routes` 不含 ai.image/embedding/rerank/audio/video 的显式路由**：`AiGenerationTaskService.submit` 通过 `apply_async(args=(task.id,), queue=f"ai.{task.task_type}")`（task_service.py:40、112）动态指定队列，但若其他地方调用 `execute_ai_generation_task.delay()` 不带 queue 参数会落到默认 `ai.chat` 队列，造成路由混乱。

---

## 维度 8：AI 工作流编排

### 实现位置

- `backend/app/modules/workflow/service/compiler.py` — `WorkflowCompiler` / `SafeEvaluator` / `safe_eval`
- `backend/app/modules/workflow/service/workflow_service.py` — `execute_llm_node` / `execute_image_generator_node` / `execute_intent_classifier_node`
- `backend/app/modules/workflow/service/checkpointer.py` — 检查点后端
- `backend/app/modules/workflow/service/event_bus.py` — 事件总线
- `backend/app/modules/workflow/tasks/workflow_tasks.py` — 工作流任务

### 治理现状

**AST 沙箱求值**：`SafeEvaluator`（compiler.py:27-128）自定义 AST 求值器，仅支持 Constant/Name/Subscript/BinOp/Compare/BoolOp/UnaryOp/Call/Attribute；`allowed_calls` 仅 `len/str/int/float/bool` 五个白名单函数。

**条件节点静态环检测**：`validate_graph`（compiler.py:222-431）做 DFS 环检测，但只对非条件节点（非 condition/intent_classifier/switch）建图。

**节点级重试**：见维度 7，指数退避，前次失败不污染 state（updates 在 return 后才 apply）。

**子图边界校验**：`_validate_subgraph_boundaries`（compiler.py:537-558）校验循环体节点不越界。

**循环/批处理硬上限**：`len(items) > 200` 抛错（workflow_service.py:478、522）；批处理 `concurrency_limit = min(max(int(config.get("concurrency_limit", 5)), 1), 20)` 限制 1-20 并发。

**AI 节点统一调用 run_ai_chat/run_ai_image**：`execute_llm_node` 和 `execute_image_generator_node` 都通过 `asyncio.to_thread` 调 `run_ai_chat` / `run_ai_image`（workflow_service.py:352、586），底层走 `AiModelRuntimeService`。

**工作流调用 skip_masking=True**：`run_ai_chat`（workflow_service.py:73）显式设 `skip_masking=True`，因为工作流节点间需要原始 PII 数据做计算。

**检查点后端可配**：`WORKFLOW_CHECKPOINT_BACKEND=sqlite|memory|postgres`，默认 sqlite 保证 Celery 多 worker/重启后 paused 实例可恢复。

**载荷冷热分离**：`PAYLOAD_STORAGE_THRESHOLD=32*1024`，单字段超 32KB 落对象存储、主表存引用。

**试运行 vs 正式执行分离**：`/trial` 跑草稿版，`/start` 跑已发布版，权限点共用 `workflow:instance:start`。

**SSE 实时进度**：`/stream` 通过 Redis pub/sub 推送节点状态迁移事件，无 Redis 时降级为心跳保活 + 进程内事件推送。

### 缺口/风险

- **工作流 LLM 节点 skip_masking 绕过 PII 脱敏**：`run_ai_chat` 设 `skip_masking=True`，若 LLM 输出直接展示给最终用户（如通过 SSE 推送），PII 会泄露。
- **模板渲染无注入防护**：`render_template`（compiler.py:153-188）用正则 `\{([a-zA-Z0-9_.]+)\}` 替换变量，变量值若含恶意内容会被直接插入 prompt，无二次转义。
- **意图分类节点无 fallback**：`execute_intent_classifier_node`（workflow_service.py:404-456）若 LLM 调用失败直接 catch 后 `matched_intent_name = "其他"`，不触发 profile 的 fallback 链。
- **Mock 工具节点**：`execute_tool_node` / `tool_web_search` / `tool_file_system` / `tool_mock_weather_api` 都是 Mock 实现（workflow_service.py:357-373、659-691），生产部署需替换为真实工具。
- **工作流执行无独立治理规则**：工作流实例调用 LLM 时，治理规则按 user_id 或 profile_id 匹配，但工作流场景下"哪个用户"可能是启动实例的管理员而非终端用户，治理规则无法按"工作流定义"维度配额。

---

## 维度 9：前端 AI 模块

### 实现位置

- `frontend/src/modules/ai/config.ts` — AI 模块注册
- `frontend/src/modules/ai/views/governance-rule.vue` — 治理规则管理
- `frontend/src/modules/ai/views/governance-event.vue` — 治理事件查询
- `frontend/src/modules/ai/views/log.vue` — 调用日志查询
- `frontend/src/modules/ai/views/dashboard.vue` — 成本看板
- `frontend/src/modules/ai/locales/{en,zh-cn,zh-tw}.json` — 国际化
- `backend/app/modules/ai/menu.json` — 菜单与权限点

### 治理现状

**治理规则 CRUD 完整**：`governance-rule.vue` 用 `useCrud` / `useTable` / `useUpsert` 实现完整增删改查，支持 scopeType/mode 过滤、编码名称搜索、启停 toggle、测试匹配。

**测试匹配对话框**：支持选用户+Profile 模拟匹配，显示命中规则数和规则明细（governance-rule.vue:35-93）。

**治理事件统计卡片**：页面顶部显示总数/拦截/告警/超限/请求/成本 6 个统计 chip（governance-event.vue:11-16），支持按事件类型和指标过滤，默认 14 天统计。

**调用日志全字段展示**：`log.vue` 表格含 15 列，顶部 6 个统计 chip（调用/成功/错误/成功率/平均延迟/Tokens）。

**成本看板多维聚合**：`dashboard.vue` 支持 groupBy=day/user/profile/model，可调 days 范围 1-365，展示 5 个汇总卡片 + 分组明细表。

**权限点完整**：`menu.json` 为每个操作配 `permission` 字段，如 `ai:governance_rule:add/toggle/match`、`ai:governance_event:stats`、`ai:log:stats`、`ai:dashboard:cost`、`ai:task:submit/cancel/retry`。

**国际化三语**：en / zh-cn / zh-tw 三套 locale 文件。

### 缺口/风险

- **所有 AI 菜单仅 admin 角色可访问**：`menu.json` 中所有菜单和按钮 `role_codes: ["admin"]`，无细分角色（如 `ai_operator` / `ai_auditor`），普通管理员无法获得只读权限。
- **治理规则表单无冲突校验**：创建规则时不校验"同一 user + 同一 period + 同一 metric"是否已存在多条规则，可能产生重复配额。
- **治理事件无导出功能**：页面仅支持分页查询和统计，无法导出 CSV/Excel 供合规审计使用。
- **调用日志无详情页**：`log.vue` 只有列表，无点击行查看完整调用详情的入口。
- **看板无图表可视化**：`dashboard.vue` 只有数字和表格，无折线图/柱状图等可视化图表。
- **成本看板与治理事件未联动**：看板显示成本，但无法点击跳转到对应的治理事件。
- **前端无 Prompt 输入校验**：`chat.vue` / `image.vue` 等调用页未在前端做 prompt 注入预检，完全依赖后端 `check_input_safety` 拦截。

---

## 维度 10：配置层面治理

### 实现位置

- `backend/app/core/config.py:Settings` — 全局配置
- `backend/app/modules/ai/config.py:MODULE_CONFIG` — AI 模块配置
- `backend/app/core/startup_checks.py` — 启动检查
- 项目根目录 `.env.example` — 环境变量示例

### 治理现状

**AI 模块独立配置**：`MODULE_CONFIG` 声明 `scopes=("admin", "aiapi")`、`middlewares=(ModuleAccessMiddleware,)`、`config_namespace="AI"`、`init_menu_file="menu.json"`（ai/config.py）。

**生产环境强制安全开关**：

- `_enforce_production_csrf`（config.py:177-185）：DEBUG=False 时强制开启 CSRF Origin 校验。
- `captcha_enabled`（config.py:222-231）：生产环境强制启用验证码，忽略 .env 配置。

**AI 相关密钥配置**：`OPENAI_API_KEY` / `OPENAI_BASE_URL` / `DEEPSEEK_API_KEY` / `DEEPSEEK_BASE_URL` / `DEEPSEEK_MODEL` / `SECRET_ENCRYPTION_KEY`（config.py:65-70）。

**限流配置可调**：`RATE_LIMIT_ENABLED` / `RATE_LIMIT_DEFAULT` / `RATE_LIMIT_ADMIN` / `RATE_LIMIT_OPEN` / `RATE_LIMIT_WHITELIST_PATHS`（config.py:113-118）。

**TaskInvoker 白名单**：`TASK_ALLOWED_SERVICES` 逗号分隔 `service_key:method` 列表，fail-closed 未列出即拒绝（config.py:127-130）。

**可信代理**：`TRUSTED_PROXIES` 逗号分隔 IP 列表（config.py:124）。

**数据库连接池治理**：`DB_POOL_SIZE=5` / `DB_MAX_OVERFLOW=10` / `DB_POOL_RECYCLE=1800` / `DB_POOL_PRE_PING=True`（config.py:150-153）；`SKIP_INDEX_ENSURE` 控制启动时是否补建索引。

**anyio 线程池**：`ASYNC_THREAD_POOL_SIZE=100`（config.py:160）。

**文件上传安全**：`UPLOAD_MAX_SIZE_MB=10`、`UPLOAD_ALLOWED_EXTENSIONS` 白名单、`MEDIA_REMOTE_DOWNLOAD_MAX_SIZE_MB=100`、`MEDIA_REMOTE_DOWNLOAD_TIMEOUT_SECONDS=30`、`MEDIA_REMOTE_ALLOWED_HOSTS="*.volces.com"`（config.py:97-105）。

**工作流配置**：`WORKFLOW_CHECKPOINT_BACKEND` / `WORKFLOW_NODE_TEST_TIMEOUT` / `WORKFLOW_NODE_TIMEOUT` / `WORKFLOW_NODE_RETRY_MAX_ATTEMPTS` / `WORKFLOW_NODE_RETRY_BACKOFF_BASE` / `WORKFLOW_EVAL_JUDGE_PROFILE` / `WORKFLOW_EVAL_REGRESSION_THRESHOLD` / `WORKFLOW_EVAL_BOOTSTRAP_SAMPLES` / `PAYLOAD_STORAGE_THRESHOLD`（config.py:48-62）。

**会话治理**：`ADMIN_SESSION_MAX_CONCURRENT=0`（0 表示不限制）、`PASSWORD_PBKDF2_ITERATIONS=210000`（OWASP 推荐）、`DOWNLOAD_TOKEN_EXPIRE_SECONDS=300`。

**日志治理**：`LOG_LEVEL` / `LOG_DIR` / `LOG_RETENTION_DAYS=30` / `RESPONSE_ENVELOPE_MAX_BYTES=2MB` / `MODULE_LOAD_STRICT=True`。

**extra="ignore"**：`Settings` 容许 .env 中存在未声明的键（config.py:279）。

### 缺口/风险

- **密钥管理无 KMS 集成**：`SECRET_ENCRYPTION_KEY` 走 .env 明文配置，无 AWS KMS / HashiCorp Vault / Azure Key Vault 集成，密钥轮换需手动改 .env 重启。
- **`OPENAI_API_KEY` 明文存 .env**：config.py:65 直接读 `OPENAI_API_KEY`，虽然 AiProvider 的 api_key 走 Fernet 加密，但全局 `OPENAI_API_KEY` 仍明文。
- **`DEFAULT_ADMIN_PASSWORD` 必填**：config.py:93 强制配置默认管理员密码，若部署后未修改存在安全隐患。
- **`RATE_LIMIT_DEFAULT=120` 偏宽松**：对管理端 60/分钟、AI 调用 120/分钟，被恶意利用时仍可在限内造成成本消耗。
- **`ADMIN_SESSION_MAX_CONCURRENT=0` 默认不限制**：多设备并行登录无限制，被钓鱼/撞库后无法通过会话数异常检测。
- **`MODULE_LOAD_STRICT=True`**：模块加载失败会启动失败，生产环境若某个非关键模块出错会导致整个服务不可用。
- **配置项无动态刷新**：除 `SysParamService` 的少数参数，大部分配置改后需重启服务，无法热更新。
- **无 secrets 扫描**：`.env` 虽在 `.gitignore`，但代码库中无 pre-commit hook 或 CI 步骤扫描硬编码密钥。

---

## 综合风险矩阵

| 维度 | 成熟度 | 关键缺口 |
|------|--------|----------|
| AI 模型管理 | 高 | 重试无 jitter、同步生图走线程池 |
| AI 安全与权限 | 高 | aiapi 限流偏松、TaskInvoker 白名单默认放行 |
| 数据安全 | 中高 | Prompt 注入字典简单、PII 类型有限、skip_masking 可绕过 |
| 审计与可观测性 | 高 | 调用日志不记 prompt 内容、错误日志可能含 PII |
| 伦理与合规 | 中低 | 无运行期内容安全检测、无偏见控制、无使用政策 |
| 成本与资源治理 | 高 | 无分级预算告警、定价手动维护、observe 无自动升级 |
| Celery 异步任务治理 | 高 | AI 队列无并发限制、任务级重试未启用 |
| AI 工作流编排 | 中高 | 工作流 skip_masking 绕过脱敏、模板渲染无注入防护 |
| 前端 AI 模块 | 中 | 仅 admin 角色可访问、无图表可视化、无导出 |
| 配置层面治理 | 中高 | 无 KMS 集成、OPENAI_API_KEY 明文、无热更新 |

---

## 关键文件清单

### 后端核心

- `backend/app/core/config.py` — 全局配置（限流/CSRF/密钥/上传/工作流）
- `backend/app/core/secret.py` — Fernet 密钥加密
- `backend/app/core/logging.py` — 结构化 JSON 日志 + contextvar 追踪
- `backend/app/celery_app.py` — Celery 队列/路由/定时任务
- `backend/app/modules/ai/model/ai.py` — AI 全部实体与 DTO
- `backend/app/modules/ai/service/governance_service.py` — 治理规则匹配/预检/并发/事件/通知
- `backend/app/modules/ai/service/security_service.py` — Prompt 注入检测 + PII 脱敏
- `backend/app/modules/ai/service/runtime_service.py` — 统一运行时 + 治理/安全/日志编排
- `backend/app/modules/ai/service/utils.py` — 成本计算/选项脱敏/窗口计算
- `backend/app/modules/ai/service/cleanup_service.py` — 治理数据定期清理
- `backend/app/modules/ai/tasks/generation_tasks.py` — AI 异步任务 CAS 抢占
- `backend/app/modules/ai/controller/aiapi/model.py` — AI 调用入口 + `require_ai_call_permission`
- `backend/app/modules/ai/controller/admin/governance_rule.py` — 治理规则 CRUD + toggle/match
- `backend/app/modules/ai/controller/admin/governance_event.py` — 治理事件查询 + stats
- `backend/app/modules/ai/menu.json` — AI 模块菜单与权限点
- `backend/app/framework/middleware/rate_limit.py` — 全局限流中间件
- `backend/app/framework/middleware/operation_log.py` — 操作日志脱敏中间件
- `backend/app/framework/middleware/scope_authority.py` — 三 scope 鉴权中间件
- `backend/app/modules/workflow/service/compiler.py` — 工作流编译器 + AST 沙箱
- `backend/app/modules/workflow/service/workflow_service.py` — AI 节点执行器
- `backend/app/modules/workflow_eval/service/evaluator/safety.py` — 安全评估器

### 前端核心

- `frontend/src/modules/ai/views/governance-rule.vue` — 治理规则管理 + 测试匹配
- `frontend/src/modules/ai/views/governance-event.vue` — 治理事件查询 + 统计
- `frontend/src/modules/ai/views/log.vue` — 调用日志查询 + 统计
- `frontend/src/modules/ai/views/dashboard.vue` — 成本看板
- `frontend/src/modules/ai/config.ts` — AI 模块注册

### 配置与基础设施

- `.env.example` — 环境变量示例
- `backend/app/core/startup_checks.py` — 启动检查
- `backend/app/modules/ai/config.py` — AI 模块配置（`MODULE_CONFIG`）
- `docker-compose.yml` — 编排文件

---

## 改进建议优先级

### 高优先级（对应生产环境安全或成本风险）

1. **补齐运行期内容安全检测**：对接 OpenAI Moderation 或阿里云内容安全 API，在 `AiModelRuntimeService` 输出阶段增加有害内容拦截（对应维度 5）。
2. **收紧 `skip_masking` 字段使用范围**：将 `skip_masking` 限制为仅内部 service 调用可设，拒绝前端请求体传入（对应维度 3）。
3. **接入 KMS 密钥管理**：将 `SECRET_ENCRYPTION_KEY` 迁移到 AWS KMS / HashiCorp Vault，实现密钥轮换（对应维度 10）。
4. **限制 AI 队列并发**：在 celery_app.py 增加 `task_annotations` 或部署文档强制要求 `-Q ai.chat -c 4`（对应维度 7）。
5. **工作流 SSE 推送 PII 脱敏**：在 SSE 事件推送前调用 `mask_sensitive_dict`，与 `skip_masking=True` 的内部调用解耦（对应维度 8）。

### 中优先级

1. **扩展 Prompt 注入检测**：引入 LLM-based 二次检测，补充 Unicode 同形字、零宽字符、Base64 编码等变形写法（对应维度 3）。
2. **扩展 PII 脱敏类型**：增加银行卡、护照、地址、IP 等类型的脱敏规则（对应维度 3）。
3. **AI 调用日志存储 prompt 摘要**：在 `AiModelCallLog` 增加 `prompt_summary` / `response_summary` 字段，便于排查问题（对应维度 4）。
4. **治理规则支持分级预算告警**：在 `AiGovernanceRule` 增加 `warn_threshold_percent` 字段，达到阈值发 warn 事件（对应维度 6）。
5. **前端细分角色**：增加 `ai_operator` / `ai_auditor` 等角色，实现只读审计权限（对应维度 9）。
6. **错误日志脱敏**：`security_service.py:81` 的 `Content Snippet` 改为脱敏后再写日志（对应维度 4）。
7. **observe 模式自动升级**：持续触发 breach 事件 N 次后自动升级为 enforce（对应维度 6）。

### 低优先级

1. **重试增加 jitter**：`_invoke_with_retry` 在固定间隔基础上增加随机抖动（对应维度 1）。
2. **成本定价自动同步**：定期从厂商 API 同步最新定价到 `AiModel.pricing_config`（对应维度 6）。
3. **治理事件导出 CSV/Excel**：前端增加导出功能，便于合规审计（对应维度 9）。
4. **看板集成图表可视化**：集成 ECharts 展示折线图/柱状图（对应维度 9）。
5. **配置热更新**：除 `SysParamService` 已支持的参数，扩展更多配置项支持热更新（对应维度 10）。
6. **CI 增加 secrets 扫描步骤**：在 CI 流水线增加 gitleaks / trufflehog 扫描硬编码密钥（对应维度 10）。
7. **拒绝词字典扩展英文**：在 `_REFUSAL_RE` 增加英文拒绝词（对应维度 5）。

---

## 总结

Loom 项目在 AI 治理领域整体工程化程度较高，最扎实的环节集中在 **成本与资源治理（维度 6）** 和 **审计与可观测性（维度 4）**：项目构建了专门的"三表模型"（`AiGovernanceRule` / `AiGovernanceEvent` / `AiRuntimeInvocation`），配合四维配额（request/token/cost/concurrent）× 三档周期（minute/day/month）× 三范围（global/user/profile）× 双模式（enforce/observe）的完整矩阵，并在并发计数上采用 fail-closed 策略、`cc_keys` 持久化精确释放、CAS 抢占防重复执行等机制，运行期治理链路从预检到后置事件闭环完整，审计日志全量记录 17 个字段并支持多维聚合看板，工程化程度在同类项目中属于较高水平。

最薄弱环节集中在 **伦理与合规（维度 5）**：项目仅有评估期的 `SafetyEvaluator` 检测 PII 泄露和 8 个中文拒绝词，运行期 AI 调用不做任何输出内容安全检测，未对接 OpenAI Moderation、阿里云内容安全等专业内容安全 API，无模型偏见控制机制，无 Usage Policy / Acceptable Use Policy 显式声明，也无端到端的"用户 → 输入 → 模型 → 输出 → 评估"完整审计链。若 Loom 用于面向 C 端的内容生成场景，需要优先补齐内容安全 API 集成和运行期输出有害内容拦截能力。

此外，**数据安全（维度 3）** 存在三个需要关注的风险点：Prompt 注入检测字典仅 9 条正则，无法覆盖 Unicode 同形字、零宽字符、Base64 编码等变形写法，且无 LLM-based 二次检测；`AiChatRequest.skip_masking` 作为请求体字段可被持有 `ai:model:invoke` 权限的用户任意开启，绕过 PII 脱敏；流式 delta 阶段不脱敏，PII 会先到达客户端并被客户端缓存，后续 `done` 事件的全量脱敏无法回收已发送内容。建议在补齐内容安全 API 的同时，同步推进 LLM-based 二次检测、加密 `skip_masking` 的使用范围（限制为仅内部 service 调用可设）、以及流式阶段的增量脱敏或客户端缓存清理机制，以将数据安全维度从"中高"提升至"高"。
