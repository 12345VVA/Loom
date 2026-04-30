# EPS (Entity Protocol Specification) 原理与操作指南

## 一、 什么是 EPS？

在传统的开发模式中，为确保前后端通信规范，我们需要使用 Swagger 文档、维护 Postman，且前端通常需要在项目里手动封装上百个 Axios 请求，并在本地大量手写 TypeScript (TS) `interface` / `type` 类型。

**EPS 全名可理解为 Entity Protocol Specification**，它是 `Loom` 体系引以为傲的最**核心技术**之一。
EPS 的核心愿景是：**彻底消灭前端对于后端简单接口的手工调用封装以及冗长数据类型的二次定义。**
其目的在于通过对后端“控制器 (Controller)”与“实体 (Entity)”等源码及其元数据（Metadata）进行强解析，最终输出给前端完整描述，让前端开箱即用、获得完美的 IDE 智能提示体验。

---

## 二、 核心原理与作用机理

EPS 的运转涵盖后端数据抽提和前端反向生成双向环节。

### 1. 后端：反射机制收集 (数据抽取原理)
在 `Loom` 这类强类型的后端架构中，借助于 TypeScript 和 Midway.js 框架自带的 **装饰器 (Decorators)** 以及 **原生 ES 标准 Reflect Metadata (元数据反射)**。

*   **执行时机**：在环境启动时进行 AST/装饰器钩子分析。
*   **提取内容**：不仅提取包含增删改查路由动作（GET, POST, 路径 /page）本身的描述；还会深度捕获被 `@Column()`、 `@Entity()` 装饰器挂载的数据库实体类，获取它们的类型与备注(`comment: "主键 ID"`)。
*   **汇总输出**：收集归纳成一个巨大且极其结构化的深度嵌套 JSON 对象树，最后将其作为内部暴露的一个规范化接口（一般开放为 `GET /admin/base/open/eps` 形式）返回给外界。

### 2. 前端：自动构建机理 (反向生成机理)
`Loom-vue` 前端体系会在执行启动（比如 `npm run dev` 运行或构建时）发起预请求。
1.  首先向后端请求拿到这颗完整的 EPS JSON 树。
2.  通过构建工具在本地自动进行扫描与归并，利用代码模板生成引擎（通常集成在框架或专属 CLI 中）：
    *   **动态生成 `.d.ts` 类型描述文件**，存放于系统约定好（类似 `.eps` / `types`）目录下。
    *   将包含 API 请求层级的字典全局挂载，使得原本需要 `axios.get('/admin/base/user/info')` 的代码演进成符合 Proxy 代理或对象树架构规范代码库。

---

## 三、 EPS 相关定义格式规范

EPS 服务给出的标准 JSON 数据大致结构必须符合以下规约（以 Loom 标准为例，仅做结构展示）：

```json
{
  "base": {
    // 根节点：属于哪一个大模块。如：base (权限基础) / task (任务字典)
    "moduleName": "base",
    "entity": {
        // [可选项]: 声明这个模块下有哪些数据库实体及其属性结构，用于前端生成类型提示
        "UserEntity": [
             {"name": "id", "type": "number", "comment": "主键"},
             {"name": "username", "type": "string", "comment": "用户名"}
        ]
    },
    "api": [
        // Controller 里的每一个暴露的路由接口节点
        {
           "method": "POST",
           "path": "/admin/base/sys/user/add",
           "summary": "新增后台用户",
           "prefix": "/admin/base/sys/user",
           "dts": {
               // 类型映射描述相关的说明对象
           }
        },
        {
           "method": "GET",
           "path": "/admin/base/sys/user/page",
           "summary": "分页查询后台用户列表"
        }
    ]
  }
}
```
只有在满足类似以上的嵌套规范时，`Loom-vue` 的前置解析逻辑组件才会成功运作，认为服务器符合自身的 EPS 标准。

Loom 当前列元数据约定：

- `source`：后端模型字段名，保持 `snake_case`，例如 `task_type`
- `prop` / `propertyName`：前端公开字段名，例如 `taskType`
- `pageQueryOp`：使用前端请求参数名，例如 `taskType`、`status`

---

## 四、 具体使用示例

通过使用 EPS 标准，你的代码逻辑将发生怎样的视觉改变？

### 传统开发模式 (Without EPS)
**前端开发者 (手写代码)：**
```typescript
import request from '@/utils/request';

// 1.痛苦地定义一遍后端早就声明过的出入参格式
export interface UserQuery {
  page: number;
  size: number;
}
export interface UserInfo {
  id: number;
  username: string;
}

// 2.痛苦地手写一遍地址与调用的服务壳子
export function getUserPage(params: UserQuery) {
  return request<UserInfo[]>({
    url: '/admin/base/sys/user/page',
    method: 'GET',
    params
  });
}
```

### Cool EPS 模式 (With EPS)
前端开发者**只需要调用**，所有的函数结构和提示由于系统已经解析 EPS JSON ，全自动产生：

```typescript
// 任意 Vue Setup 业务组件下

import { useCool } from "/@/cool"; // 引入系统

const { service } = useCool(); // 这是自动从 eps 树构建出的巨大的、层级化的全局网关

// 极速调用，并且具备了上述所有 TypeScript 类型提示！！
const users = await service.base.sys.user.page({
   page: 1,
   size: 20
});
console.log(users.data); 
```
如上面的示例所示：
通过 `.base.sys.user.page()` 前端能够**闭着眼睛根据语法提示（点点点）**精准触发 API 请求，且参数类型能够得到 IDE 最严苛审查保护，这极大节省了工作效率。

---

## 五、 Python(FastAPI) 的 Loom 如何实现这类效果

FastAPI 中存在 OpenAPI / Swagger，但 Loom 当前并不是简单把 Swagger “伪装”为 EPS。实际实现会组合以下来源：

- `CoolControllerMeta` 导出的控制器、CRUD、权限和查询元数据
- `scan_model_columns()` 扫描 Pydantic / SQLModel 字段
- `resolve_alias()` 输出前端公开字段名
- FastAPI OpenAPI 信息作为补充

最终由 `/admin/base/open/eps` 输出 Loom 前端可识别的数据结构。字段语义保持：

- `source`：后端模型字段名
- `prop` / `propertyName`：前端公开字段名
- `pageQueryOp` / `listQueryOp`：前端请求参数

Swagger 仍然保留给 `/docs`、`/redoc` 和通用 OpenAPI 工具使用；Loom 前端优先消费 EPS。
