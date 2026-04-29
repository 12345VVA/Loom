# Cool-Admin 权限中间件原理与操作指南

## 一、 什么是 Cool 权限中间件？

在 `cool-admin-midway` （基于 NodeJS 系列）的架构中，权限中间件是安全访问中枢。它串联了在后端拦截请求时的“身份认证 (Authentication)” 与 “行为授权 (Authorization)” 两个部分。

不同于传统 Python Web 框架将鉴权仅仅作为一个纯粹的阻断层，依赖 Midway.js IoC 机制构建的 Cool 权限中间件在处理拦截鉴权的同时，与应用依赖注入的“上下文 (Context)”深度整合，随时通过 AOP 对后续经过权限层的方法赋予操作者（用户）数据信息。

---

## 二、 核心原理与作用机理

### 1. 工作原理 
利用 Web 框架标准的中间件洋葱圈模型，结合 JWT 的自包含特性及 Redis 的高效状态查询。
1. **统一拦截门面：** 所有外部进入例如 `/admin/*` 前缀的请求强制穿越由该中间件编排的过滤器层。
2. **切面反射提取目标权限：** 配合 TypeScript 反射特性，在拦截阶段该请求未命中真正的控制器业务逻辑前，中间件就能反推查明这次 HTTP 触达的路由将要映射进哪个目标 Controller。而控制器类和方法上的 `@CoolController({ api: ['add'] })` 隐式绑定了诸如 `(某模块):(某业务):add` 的目标要求权限点。

### 2. 作用机理（执行流）
每一次后台系统的请求抵达后端，将发生如下流程：

*   **Step 1: 白名单短路检查**
    判断当前路由路径是否处在框架声明的“公开白名单（如 `/admin/base/open/login`）”中，如果符合直接 `return await next();` 跳过后面的检查流程。
*   **Step 2: 凭证提取解码**
    统一从请求头提取 `Authorization: Bearer <Token>` 结构的内容。如果没有则立刻触发拦截外抛 `HTTP 401（状态错误被拦截，前端将触发退回登录页逻辑）`。
*   **Step 3: 状态检查（Redis 比对）**
    为防止修改密码后失效、主动登出后继续访问、或会话并发超限，系统会校验 Token 中的 `password_version`、`token_version`、`jti`，并与 Redis 中的登录态、黑名单和会话缓存进行比对。API JSON 字段可以映射为 `passwordVersion`，但 Token 载荷内部统一使用 `snake_case`。
*   **Step 4: 具体功能比对（权限检查）**
    利用上面提到的提取出本请求“所需期望达成的权限标志位”，直接比对系统对该 Token 预存在缓存中的“具有完全权限列表字符串”。如果是超管可以直接跳过所有比对，如果普通用户未命中此字符串，抛出 `HTTP 403 (无越权访问)`。
*   **Step 5: Context 信息植入**
    将解析出的有效的当前操作人 ID 或者基本信息字典附加到类似 Midway.js 的 `ctx.admin` 等系统全局单次调用的会话对象上。接下来的所有底层业务都可以不需要取 token，直接从 `ctx.admin.userId` 获取数据做数据库增改查。

---

## 三、 权限中间件相关规范要求

使用或针对该特性进行开发对接时，需牢记几个核心的规范约定规则。

### 1. Token 传递约定协议
前端统一通过标准的 Auth 请求形式发放，必须满足规范，比如不能混加额外字符：
```http
Authorization: Bearer eyJhbGciOiJI.........(token_body)...............
```

### 2. 响应阻断 Code 规范（核心）
中间件阻断行为不仅返回给浏览器，必须适配 `cool-admin-vue` 前端内部硬编码好（可配置改）的响应识别条件。
- 当 `code === 401` 或业务代号包含约定的非法请求代号时，意味着 Token 破晓，前端会强制弹回至包含 `/login` 的登录大屏页，并清理本地缓存。
- 当 `code === 403` 返回时，前台将保留原地组件视图，通常会弹窗红框 Alert（"您暂无访问该资源的权限，请求被服务器拒绝"）。

### 3. URL 与权限字符绑定的隐性映射标准
`cool-admin` 内置有一个极简的前后端约束规范。路由路径的动作往往和权限字符串有高度的语义绑定。
- 例如模块名叫 `sys`，资源名叫 `user`，前端所配的一级权限可能叫 `base:sys:user`。
- 如果请求了 `/admin/base/sys/user/add`，中间件一般会映射期望用户拥有 `base:sys:user:add` 的细粒度权限串才能通过放行。

---

## 四、 具体使用示例

### 1. 在 Midway 中装配/配置中间件白名单
作为开发者，在原版 TS 代码中，通常会在框架的配置文件 (`config.default.ts`) 设置中间件选项，指引它的运行状态与哪些口子需要放行：

```typescript
// src/config/config.default.ts
export default {
  // ...其它配置
  cool: {
    // 路由相关配置控制
    router: {
      // 在这里添加忽略鉴权的路由，它们穿越权限中间件时将不受到校验
      ignore: [
        "/admin/base/open/login", 
        "/admin/base/open/eps"
      ]
    }
  }
}
```

### 2. Controller 接口级别对权限的要求约束 
对于需要额外防护的接口，或是使用了 EPS 自动化接口：

```typescript
// 通过框架特有的机制，申明 Controller 
// 下方代表通过该控制器的请求除了基础角色，甚至不需手动写权限代码，框架自己会给它配置需要 base:sys:user:(某个操作)
@CoolController({
  api: ['add', 'delete', 'update', 'info', 'list', 'page'],
  entity: UserEntity,
  // 甚至可以直接在控制器级传递额外装饰控制或过滤权限功能
  // ...
})
export class BaseSysUserController extends BaseController {}

// 若你手动书写一个功能，通过其内置框架上下文拿出了权限身份：
@Post('/syncData', { summary: '同步关键平台数据' })
async sync() {
  // Context 被权限中间件注入后，内部提取超方便。
  const userId = this.ctx.admin.userId;   
  
  // 内部进行业务逻辑操作时直接取用该用户信息
  await this.syncService.handle(userId);
  return this.ok("同步成功");
}
```

### 3. 伴随后端这套权限体系的“前端按钮展示保护”
它在后端的表现为抛出 403，在前端由于 EPS 已将上述约束字典抛给 Vue，往往只需在按钮上贴标，没有权限的人甚至连发送错误请求进入中间件的红按钮都看不到。

```vue
<!-- 前端视图开发：如果该用户被中间件在 `/admin/base/open/person` 时下发的字典里没包含下面这条记录 -->
<!-- 按钮将直接消失或者变成灰色，彻底断绝越权操作产生的可能 -->
<el-button 
  v-permission="'base:sys:user:add'" 
  type="primary" 
> 
  新建管理员成员
</el-button>
```

#### Loom 当前实现

当前 Loom 的 FastAPI 中由 `ScopeAuthorityMiddleware`（见 `app/framework/middleware/scope_authority.py`）统一处理 `/admin`、`/app`、`/aiapi` scope。它会完成白名单、Token、Redis 登录态、URL pattern 权限和 `request.state.current_user` 注入。

响应包装已经由 `ResponseEnvelopeMiddleware` 统一输出 Cool Admin 前端可识别的 `{ code, message, data }` 结构；权限点则由 `CoolControllerMeta`、自定义路由 `permission` 和 `menu.json` 共同对齐。
