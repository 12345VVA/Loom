# Loom 后端与 Cool-Admin 核心机制差异深度对比及迁移对齐指南

## 第一部分：核心运行机制差异深度剖析

Loom 项目（基于 Python 的 FastAPI + SQLModel）与 `cool-admin-midway`（基于 Node.js 的 Midway.js + TypeORM）虽然都旨在解决后台管理系统的快速开发，但受限于语言生态与框架底层哲学，两者的核心业务机制存在巨大的本质差异。了解这些差异是顺利进行迁移适配的前置条件。

### 1. 权限中间件处理 (Middleware Handling) 核心差异
*   **Loom (FastAPI - 偏向网关层物理拦截):**
    在 FastAPI 中，中间件 (`BaseHTTPMiddleware`) 位于整个 ASGI 网络请求的最外围。Loom 通过 `AdminAuthorityMiddleware` 拦截所有的 `/admin/*` 前缀请求。它的鉴权是非常纯粹的“请求-头信息拦截”。Loom 先从请求中提取 Token，直接从 Redis 缓存提取或判定当前用户是否登录，随后进行 HTTP 原生级别的权限抛出异常（`raise HTTPException`）。
*   **Cool-Admin (Midway.js - 偏向 AOP 与依赖注入环境拦截):**
    依赖于 Midway 强大的 AOP（面向切面编程）能力及其 Web 层的 Guard (守卫) / Filter (过滤器)。权限的校验通过 `@CoolController` 结合内部鉴权上下文 (ctx) 工作。它不仅仅是网络层的阻断，中间件可以直接利用内部容器（IoC Container）随时取出对应的 Service 实例提取配置与验证路由拦截。

### 2. 权限体系设计 (Permission System Design) 核心差异
*   **Loom (扁平化通配符式权限):**
    采用的是由 `loader.py` 定义并生成资源的基于 **URL 通配符匹配 (fnmatch)** 方案。在运行时，某个用户的菜单权限被转化为类似于 `["GET /admin/base/user/*", "POST /admin/base/role/*"]` 这样的模式规则缓存到 Redis 中。任何用户的触达，核心校验算法依据是“以请求 URL 比对正则表达式/通配符池是否匹配”。
*   **Cool-Admin (严格的方法实体级权限树):**
    采用的是更为传统的“节点/动作”授权模式。后台路由在生成时默认映射了具体的增删改查动作代码。权限被明确定义为“按钮或行为粒度”的字符串标识符（如 `base:user:update`），且这种控制不仅是后端的检查依据，该标识符还必须一对一原样传输给前端，用于激活前端 Vue 的指令从而控制按钮显示。

### 3. 模块化设计 (Modular Design) 核心差异
*   **Loom (自定义静态加载器约束):**
    由于原生 Python 缺乏 Java / C# 级别标准的 IoC 容器生态，Loom 使用了自己实现的包文件遍历机制 (`app.modules.loader`) 。通过硬性要求每个业务模块必须存放一个 `config.py` 文件（暴露 `ModuleConfig` 数据结构）去声明白名单和路径。这种机制极度轻量，它仅仅起到了“注册表收集”的功能。
*   **Cool-Admin (基于强类型与 IoC 容器的高度内聚):**
    高度受惠于 TypeScript 的元数据发射（`reflect-metadata`）与 Midway IoC。只要放置一个模块包，里面的控制器 (`Controller`) 、服务类 (`Service`) 甚至数据库实体类 (`Entity`) 会根据各自使用的装饰器自动注入对应上下文。它自带完整的生命周期系统支撑。

### 4. 自动路由技术 (Automatic Routing Technology) 核心差异
*   **Loom (文件路径映射收集式路由):**
    Loom 的 `auto_router.py` 工作原理是：根据你书写的控制器在文件系统的真实路径（如 `modules/base/controller/admin/user.py`）自动推断应该使用 `/admin/base/user` 前缀。然后它动态引入（`import_module`）文件里面暴露写好的 `router: APIRouter`。**核心在于：Loom 的自动路由目前只节省了前缀引用的时间，并没有自动化生成接口的代码实现。**
*   **Cool-Admin (面向接口元数据的 CRUD 自动扩充引擎):**
    Cool-Admin 下，通过书写 `@CoolController({ api: ['add', 'delete', 'update', 'info', 'list', 'page'], entity: UserEntity })`。框架在启动时，除了会依据名字生成路由，还会通过 AOP 植入底层已写好的继承实现（`cl-crud` 的 6 个增删改查实现方式会被注入到当前的路径规则下），开发者甚至不用写任何一句 Python 里的 `def` 或者函数体。

### 5. EPS 技术 (Entity Protocol Specification) 核心差异
*   **Loom (采用 OpenAPI 降级):**
    Loom 体系且没有提供自研的专用类型通讯规约。它是利用标准 FastAPI 产生的 `openapi.json` 结合 Pydantic 提供前端所需要的请求与接收格式要求。若没有特殊工具介入，前端必须要借助如 swaggert-codegen 的方式来实现客户端函数映射。
*   **Cool-Admin (深度自研的闭环 EPS 跨端协议):**
    EPS (类型说明和定义生成协议) 是 Cool 的灵魂。后端中间件在启动初始化时，通过 TypeScript 逆向读取每一个实体及 Service 上定义的强类型描述并且直接汇聚成 `/admin/base/open/eps` 接口；而前端框架一旦请求该接口拿到数据包，不但可以获取请求函数映射字典，更是可以直接动态在页面生成一个深度的全套类型文件库供在 IDE 里辅助编码，消灭前后端沟通壁垒。

---

## 第二部分：前端完全替换为 cool-admin-vue 迁移对齐行动指南

在理解了核心机制差异后，我们需要通过“桥接器思维”而非“大规模修改原生 Python 框架思维”来把您的后端包装成“伪造的 Cool-Admin” 以供 `cool-admin-vue` 前端无缝拉起。

### 对接点一：重构全局响应返回格式 (API Payload Wrap)
前端中内置的 axios 拦截器死死咬住了标准的 JSON 包一层模式：
如果直接用现在的 FastAPI 可能会返回：
`{"id": 1, "name": "test"}`。
而要使用 `cool-admin-vue`，你需要增加一个由 FastAPI `Route` 类自定义或者更低层的中间件来将所有的 `dict` 和 `pydantic` 截获，改为：
```json
{
  "code": 1000, 
  "message": "success", 
  "data": {"id": 1, "name": "test"}
}
```
**注意：** 如果使用分页 `/page` 查询，除了状态码，内置 `cl-crud` 需要的数据结构为：
`"data": { "list": [...], "pagination": {"page": 1, "size": 20, "total": 100} }`

### 对接点二：模拟 Cool 核心组件级自动化路由 (Mock CRUD router)
因为 Loom 下并没有 `@CoolController` 能够平空变出 `/page`, `/delete` 接口的代码实现。在不动大量 Python 架构的情形下：
你需要抽象一个高级 Router，例如在 `app/framework/router` 下编写一个 `crud_router.py`，暴露一个方法 `generate_crud_router(model: SQLModel, db_session) -> APIRouter`，并自动生成挂载标准命名的 `page`, `list`, `info`, `add`, `update`, `delete` 等方法接口供各个 Module 使用，这样来补平两者**自动路由机制上的差距**。

### 对接点三：伪造关键模块入口与 EPS 结构支撑
前端完全不用改动（开箱即用）的前提，就是后端的服务端口全部模拟成标准输出。需要提供：
1. ** `/admin/base/open/login`**：需返回包含 `token` 的字段结构。
2. ** `/admin/base/comm/person` 以及权限口**：需能返回包含 `menus` 子树与诸如 `['base:user:update']` 此类一维数组的权限标识，此权限控制差异点会在此接合（您要实现 URL 通配转化权限位的转换器）。
3. **关键技术实现：利用 OpenAPI 重构输出适配 EPS (/admin/base/open/eps)**
由于我们采用 Python，没有自研的 EPS 引擎机制，我们可以 **将 FastAPI 的 Swagger 数据包伪装为 EPS 结构格式返回：**
您需要新增一个后端 API 例如 `get_eps()`:
在内部，请求：`fastapi.openapi.utils.get_openapi(title="...", version="...")`。
通过遍历这个对象里的 `paths`、`components`，写一组 Python 迭代代码，将它拼接转换为 Cool-Admin 识别的如 `{[module]: {api: ... }` 格式（具体格式您可以抓包一次线上 demo.cool-js.com 获取）当作普通 json 吐出。
只要有了这个桥接动作，`cool-admin-vue` 在前端启动阶段即可正常推演，这彻底填平了**EPS 协议不对称带来**的沟通障碍。

### 总结
你现在的路线非常明确：保留原有的 Loom 性能底基和包挂接体系，但是给外部 API 层披上一套“中间代理外衣”并增加特定的基础 `/admin/base` 系列数据支撑能力。前端拿到这些熟悉的响应与桥接结构时，即可直接运用现成组件生态。
