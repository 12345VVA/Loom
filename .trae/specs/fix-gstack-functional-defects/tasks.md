# Tasks

## 阶段 1：文档订正

- [x] Task 1: 更新 `deliverables/gstack/功能缺陷.md` 核实摘要表
  - 标注 #1/#2 已修复（annotation-drawer 完整上下文 + 自动 caseResultId 注入）
  - 修正 #3 LLM 降级描述（已串联：`run_ai_chat` / `run_ai_image` 桥接）
  - 在 #4 节点 SDK 缺失条目下注明本次不修复原因
  - 在 #5/#6/#7 条目下标注「本次修复」
  - 在 #8/#9/#12 条目下标注「本次不修复」原因
  - 节点清单修正：Loop 已存在，仍缺 HTTP / DB Query

## 阶段 2：可视化调试补全（#6）

- [x] Task 2: 后端透传 `failed_node_id`
  - `WorkflowInstanceRead` DTO 增加 `failed_node_id: str | None = None` 字段（API 响应序列化为 `failedNodeId`）
  - SSE `failed` 事件 payload 增加 `node_id`（3 处：`_mark_instance_failed`、超时分支、except 分支）
  - 验证：`pytest tests/test_workflow_*.py` 通过

- [x] Task 3: 前端实例列表展示失败节点
  - `instance.vue` 表格新增「失败节点」列（`el-tag type="danger"` 包裹，仅 status=failed 时展示）
  - 验证：`npm run type-check` 通过

- [x] Task 4: 试运行画布失败节点定位与错误展示
  - `useWorkflowTest.ts` 新增 `markFailedNode(nodeId, errorMessage)`，SSE `failed` 事件即时高亮失败节点 + 写入 errorMessage
  - `base-node.vue` 节点浮层在 status=error 时展示错误信息（WarningFilled 图标 + 红色块）
  - `updateNodeStatus` 加时序保护，防止 logs 刷新清掉 SSE 写入的 errorMessage
  - 验证：`npm run type-check` 通过

## 阶段 3：告警通知接入（#7）

- [x] Task 5: 新增 `workflow.failed` 通知模板初始化
  - `backend/app/modules/workflow/config.py` 新增 `bootstrap(session)` 函数，幂等创建 `NotificationTemplate`（code=`workflow.failed`）
  - `MODULE_CONFIG` 注册 `bootstrap="app.modules.workflow.config.bootstrap"`
  - 模板字段：`title_template="工作流「{workflow_name}」执行失败"`、`content_template="实例 #{instance_id} 在节点 {node_id} 失败：{error_message}"`

- [x] Task 6: 工作流失败分支调用 NotificationService
  - 新增 `_notify_workflow_failure(instance_id)` 辅助函数（独立 session，调 `render_template` + `send_business`）
  - 3 处失败分支（`_mark_instance_failed`、超时分支、except 分支）调用通知
  - 接收人为 `instance.user_id`（实际字段名，对应 spec 中的 `created_by`）
  - 通知调用 try/except 包裹，异常仅记 warning，不影响主流程
  - 验证：新增 `test_workflow_failure_notification.py` 11 个测试全部通过；现有 workflow 测试 34 个通过

## 阶段 4：标注沉浸式队列（#5）

- [x] Task 7: `annotation-drawer.vue` 支持队列导航与快捷键
  - 新增 props：`caseResults?: WorkflowEvalCaseResult[]`、`initialIndex?: number`（保留原 `caseResultId`/`context` 兼容）
  - 新增内部状态：`currentIndex`、`total`、`isQueueMode`、`currentCase`、`currentCaseResultId`、`currentContext`
  - 底部新增「上一条 / X/Y / 下一条」导航条
  - 全局 keydown 监听：P=Pass、F=Fail、J/→=下一条、K/←=上一条、Enter=提交并下一条
  - 焦点在 input/textarea/contenteditable 时单字母快捷键不触发；textarea 中 Enter 保留换行
  - `submitAndNext`：提交成功后非末条 goNext，末条 ElMessage.success + 关闭
  - 验证：`npm run type-check` 通过

- [x] Task 8: `run.vue` 透传队列数据到抽屉
  - 新增 `annotationQueue` + `annotationInitialIndex` 响应式状态
  - `openAnnotation(row)` 用 `detail.cases` 作为队列源，`findIndex` 定位初始索引
  - 模板新增 `:case-results` + `:initial-index` 绑定，保留原 props 向后兼容
  - 验证：`npm run type-check` 通过

## 阶段 5：验证

- [x] Task 9: 后端测试
  - `pytest tests/test_workflow_failure_notification.py` — 11/11 通过（新增）
  - `pytest tests/test_workflow_p0_fixes.py` + `test_workflow_retry.py` + `test_workflow_execution.py` — 34/34 通过
  - `pytest tests/test_workflow_annotation.py` — 通过
  - `pytest tests/test_framework_alignment.py` — 8 个失败，全部是 PostgreSQL 连接错误（`192.168.99.175:5433` 连不上），环境问题，与本次改动无关
  - 失败节点透传单测、失败通知触发单测：已新增并全部通过

- [x] Task 10: 前端类型检查
  - `npm run type-check`（vue-tsc --build --force）exit code 0，通过
  - 无类型错误

# Task Dependencies

- Task 2 → Task 3、Task 4（前端依赖后端 DTO/SSE 字段）
- Task 5 → Task 6（通知调用依赖模板初始化）
- Task 7 → Task 8（抽屉改造先于 run.vue 联动）
- Task 9 依赖所有后端任务（Task 2、5、6）
- Task 10 依赖所有前端任务（Task 3、4、7、8）
- Task 1（文档订正）独立，可并行
