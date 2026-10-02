# Loom 文档索引

本文档目录只保留当前有效的框架说明、开发规范和运维测试说明。历史分析、迁移过程稿和已完成的补丁清单已从仓库删除，必要时通过 git 历史追溯。

## 核心说明

1. [框架说明文档](./框架说明文档.md)  
   框架权威总览：模块加载、自动路由、CRUD、鉴权、EPS、QueryBuilder、DataScope、缓存、存储、监控与当前边界。

2. [模块自动路由与管理端鉴权说明](./模块自动路由与管理端鉴权说明.md)  
   模块目录约定、路由生成规则、权限注册、动态菜单和新增模块方式。

3. [权限管理与登录模块设计](./权限管理与登录模块设计.md)  
   登录、Token、Redis 缓存、会话控制、RBAC、DataScope、审计和登录安全增强。

4. [EPS规范原理与操作指南](./EPS规范原理与操作指南.md)  
   EPS 输出结构、字段语义、前端 service 衔接方式。

5. [字段映射使用规范](./字段映射使用规范.md)  
   后端 `snake_case` 与前端 Loom 字段别名的边界，以及 `source`、`prop`、`propertyName` 的使用口径。

6. [通知系统框架说明](./通知系统框架说明.md)  
   站内通知、业务通知、任务通知、受众规则、模板和任务通知配置说明。

## 业务模块架构

- [AI 与工作流系统架构说明](./AI与工作流系统架构说明.md)
  以主干代码为准的 `ai` / `workflow` / `task` 三模块架构：三层配置、12 家厂商适配器、`AiModelRuntimeService` 统一运行时、LangGraph 编译型工作流引擎、Celery 队列与 Beat 定时、通用系统定时任务调度器；文末附与其他失真分析版本的差异对照。

- [工作流观测与评价系统性能优化建议](./工作流观测与评价系统性能优化建议.md)
  工作流观测（节点/实例追踪、SSE、统计看板）与评价（自动评估、批量回归）的性能诊断：统计全表聚合、async 执行体内同步阻塞、SSE 订阅占线程池、前端轮询未用 SSE；建议按"同步 `def`+`to_thread` 卸载"的项目既定方向落地，评价侧推荐集成 Langfuse。附对两份原始分析的采纳与勘误。

## 开发规范

- [框架Controller使用规范](./框架Controller使用规范.md)
- [框架Service使用规范](./框架Service使用规范.md)
- [框架Model使用规范](./框架Model使用规范.md)

## 运维与测试

- [自动化测试使用说明](./自动化测试使用说明.md)
- [系统任务配置说明](../backend/docs/01-系统任务配置说明.md)
- [CI 设计（2026-10-02）](./CI设计-2026-10-02.md)
  GitHub Actions 双 job（backend 挂 postgres:16 service + Celery 完整性校验 / frontend type-check + lint:check + vitest + build）的完整 workflow YAML；含四个关键设计决策、conftest 测试库防护，以及"双轨 → 参数化 → SQLite 退场"三步走路线与终态收尾清单。

## 代码审查

- [Workflow 模块代码审查（2026-06-22）](./workflow-audit-2026-06-22.md)
  工作流模块全量审查：7 个严重（IDOR/PII/checkpointer/取消/并发/resume/删分支残留）+ 11 中等 + 10 轻微，每条带【未修复】状态标记，用于追踪修复进度。

- [架构与治理评审（2026-10-02）](./架构与治理评审-2026-10-02.md)
  全项目三维度评审（后端架构 6.5 / 前端架构 7 / 治理 6）：P0 无 CI 门禁、P1 分层反向依赖与审计日志疑似丢失、P2 三套 schema 并存与供应链零锁定等问题清单 + 9 条按性价比排序的行动建议，逐条带【待处理】标记与勾选框，用于追踪整改进度。

## 当前框架口径

- 管理端路径统一使用 `/admin/{module}/{resource}/{action}`。
- 标准 CRUD 的 `list/page` 同时支持 GET 和 POST，POST 是 Loom 与 EPS 主协议。
- 响应 JSON 保持 `{ code, message, data }` 包装；大 JSON 超过阈值时跳过包装。
- 模型和 Service 内部使用 `snake_case`；API 响应与 EPS 的 `prop/propertyName` 输出前端字段名；`source` 保留后端字段名。
- 权限点统一使用 `{module}:{resource}:{action}`，后端中间件和前端 `v-permission` 使用同一字符串。
- Redis 是权限缓存和会话状态的首选存储；开发环境 Redis 不可用时降级为进程内缓存。
- `/health` 提供 DB、Redis、Celery 配置检查；`/metrics` 由 `METRICS_ENABLED` 控制。

## 历史已删除说明

阶段性分析、迁移方案和已完成补丁记录已合并进当前说明或删除；需要追溯时请查看 git 历史。
