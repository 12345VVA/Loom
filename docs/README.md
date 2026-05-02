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

## 开发规范

- [框架Controller使用规范](./框架Controller使用规范.md)
- [框架Service使用规范](./框架Service使用规范.md)
- [框架Model使用规范](./框架Model使用规范.md)

## 运维与测试

- [自动化测试使用说明](./自动化测试使用说明.md)
- [系统任务配置说明](../backend/docs/01-系统任务配置说明.md)

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
