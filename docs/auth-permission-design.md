# Loom 权限管理与登录模块设计

## 1. 设计目标

结合参考文档里的思路，Loom 首期权限体系采用：

- 登录认证层：`JWT Access Token + Refresh Token`
- 授权层：`RBAC`
- 数据范围层：`Role -> Department`
- 业务快捷标记层：`is_super_admin / is_manager / is_department_leader`

但考虑 Loom 当前还处于早期阶段，首期不直接照搬“JWT + Redis 登录态缓存”的完整形态，而是采用两阶段推进：

- Phase 1：先落库模型、登录接口、权限依赖、默认管理员和任务模块权限保护
- Phase 2：再补 Redis 会话态、单点登录、权限缓存刷新、统一数据权限注入

这样做的原因很直接：目前项目只有任务模块，没有用户后台、角色后台、菜单后台。如果现在就把完整缓存态和复杂中间件一次性做满，代码会明显超前于业务。

## 2. 权限模型

### 2.1 主体与资源

- 用户：`sys_user`
- 角色：`sys_role`
- 菜单/权限资源：`sys_menu`
- 部门：`sys_department`

### 2.2 关系表

- 用户角色：`sys_user_role`
- 角色菜单：`sys_role_menu`
- 角色部门：`sys_role_department`

### 2.3 与参考方案的一致点

- 权限主链路仍然是 `User -> Role -> Menu(permission)`
- 菜单表同时承担权限资源定义职责
- 部门不是接口权限边界，而是数据权限边界
- 保留管理身份字段，方便后续业务快速做二次控制

### 2.4 与参考方案的差异

- 当前未引入 Redis 权限缓存
- 当前未做全局中间件 URL 匹配授权，而是采用 FastAPI 依赖式权限声明
- 当前数据权限先以内聚在 Service 中的过滤逻辑实现，后续再抽统一注入层

## 3. 登录链路

### 3.1 登录接口

`POST /admin/base/open/login`

请求：

```json
{
  "username": "admin",
  "password": "Admin123456"
}
```

返回：

- `access_token`
- `refresh_token`
- 当前用户资料
- 当前权限点列表

### 3.2 Token 载荷

Access Token / Refresh Token 统一包含：

- `sub`: 用户 ID
- `type`: `access` 或 `refresh`
- `password_version`

Access Token 额外包含：

- `username`

### 3.3 失效策略

首期采用：

- Token 到期自动失效
- 修改密码后 `password_version + 1`，旧 token 全部失效

二期再补：

- Redis 会话态
- 主动登出失效
- 单设备 / 多设备策略

## 4. 授权链路

### 4.1 当前方案

通过 FastAPI 依赖做声明式授权：

```python
Depends(require_permission("tasks:create"))
```

优点：

- 直观
- 易于逐步落地
- 不需要先构建复杂中间件和白名单管理

缺点：

- 不能像参考系统那样自动按 URL 统一拦截
- 对接口声明规范有依赖

### 4.2 后续演进

当管理后台和接口规模上来后，可以切换到：

- 全局鉴权中间件
- 路由白名单
- 权限点缓存
- URL 与 `perms` 自动匹配

## 5. 数据权限

首期原则：

- 超管可查看全部任务
- 普通用户仅查看自己的任务

这相当于先实现最小化的数据域控制，为后续部门权限做落点。

后续扩展顺序建议：

1. 用户绑定部门
2. 角色绑定部门范围
3. `data_scope` 从 `self` 扩展到 `department` / `department_and_children` / `all`
4. 统一抽象 `DataScopeResolver`

## 6. 首期默认角色与权限

### 6.1 默认角色

- `admin`：系统管理员，拥有全部权限
- `task_operator`：任务操作员，拥有任务查看、创建、取消权限

### 6.2 默认权限点

- `tasks:read`
- `tasks:create`
- `tasks:cancel`

## 7. 首期落地范围

本次已落地或准备落地的范围：

- 用户/角色/菜单/部门/关系表模型
- 默认管理员初始化
- JWT 登录与刷新
- 当前用户 `/admin/base/user/me`
- 任务接口接入认证和权限点校验
- 任务列表按“本人 / 超管”做数据隔离

暂不在本次实现范围内：

- 前端登录页与 Pinia 登录态管理
- 用户管理后台
- 角色管理后台
- 菜单管理后台
- Redis 会话缓存
- 验证码/短信登录
- 统一数据权限注入框架

## 8. 后续建议

建议下一步按这个顺序继续：

1. 先补前端登录页、路由守卫、认证 store
2. 再补用户管理与角色管理 API
3. 然后把权限点配置从代码初始化迁到可管理后台
4. 最后再接 Redis，会话态和权限缓存一起上
