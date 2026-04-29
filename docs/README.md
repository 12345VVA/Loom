# Loom 文档索引

## 推荐阅读顺序

1. [框架说明文档](./框架说明文档.md)
   核心机制总览：模块、自动路由、CRUD、鉴权、EPS、QueryBuilder、DataScope、基础设施。

2. [模块自动路由与管理端鉴权说明](./模块自动路由与管理端鉴权说明.md)
   路由目录约定、权限注册、菜单权限、动态菜单与新增模块方式。

3. [权限管理与登录模块设计](./权限管理与登录模块设计.md)
   登录、Token、Redis 缓存、会话控制、RBAC、DataScope 与审计。

4. [EPS规范原理与操作指南](./EPS规范原理与操作指南.md)
   EPS 输出结构、字段语义、前端 service 衔接方式。

5. [字段映射使用规范](./字段映射使用规范.md)
   后端 `snake_case` 与前端 Cool Admin 字段别名的边界。

## 开发规范

- [框架Controller使用规范](./框架Controller使用规范.md)
- [框架Service使用规范](./框架Service使用规范.md)
- [框架Model使用规范](./框架Model使用规范.md)

## 对齐与升级记录

- [框架待升级与补丁清单](./框架待升级与补丁清单.md)
- [后端与 Cool-Admin 核心机制差异及当前对齐状态](./后端核心机制差异与迁移指南.md)
- [后端技术对比分析报告](./后端技术对比分析报告.md)
- [兼容写法深度分析与解决方案](./兼容写法深度分析与解决方案.md)
- [Cool权限中间件原理与操作指南](./Cool权限中间件原理与操作指南.md)

## 模块文档

- [系统任务配置说明](../backend/docs/01-系统任务配置说明.md)

## 当前框架口径

- 管理端路径统一使用 `/admin/{module}/{resource}/{action}`。
- 标准 CRUD 的 `list/page` 同时支持 GET 和 POST，POST 是 Cool Admin 与 EPS 主协议。
- 响应 JSON 保持 `{ code, message, data }` 包装。
- 模型和 Service 内部使用 `snake_case`；API 响应与 EPS 的 `prop/propertyName` 输出前端字段名；`source` 保留后端字段名。
- 权限点统一使用 `{module}:{resource}:{action}`，后端中间件和前端 `v-permission` 使用同一字符串。
- Redis 是权限缓存和会话状态的首选存储；开发环境 Redis 不可用时降级为进程内缓存。
