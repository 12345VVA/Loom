# Checklist

## 阶段 1：文档订正
- [x] `功能缺陷.md` 核实摘要表更新为 2026-07-02 状态，#1/#2 标注已修复
- [x] `功能缺陷.md` #3 LLM 降级描述更正为「已串联」
- [x] `功能缺陷.md` #5/#6/#7 条目下标注「本次修复」
- [x] `功能缺陷.md` #4/#8/#9/#12 条目下标注「本次不修复」及原因
- [x] `功能缺陷.md` 节点清单修正（Loop 已存在，缺 HTTP/DB Query）

## 阶段 2：可视化调试补全（#6）
- [x] `WorkflowInstanceRead` DTO 包含 `failed_node_id` 字段（API 响应 `failedNodeId`）
- [x] SSE `failed` 事件 payload 包含 `node_id` 字段（3 处：`_mark_instance_failed`、超时分支、except 分支）
- [x] `instance.vue` 列表在 status=failed 行展示失败节点（`el-tag type="danger"`）
- [x] `useWorkflowTest.ts` 处理 `failed` 事件时根据 `node_id` 高亮失败节点（`markFailedNode`）
- [x] `base-node.vue` 节点浮层在 status=error 时展示错误信息（WarningFilled 图标 + 红色块）
- [x] `pytest tests/test_workflow_*.py` 通过（45/45，含新增 11 个 + 现有 34 个）
- [x] `npm run type-check` 通过

## 阶段 3：告警通知接入（#7）
- [x] `workflow.failed` 通知模板初始化幂等（`bootstrap` 函数先查 code 不存在才插入）
- [x] 模板包含 `workflow_name` / `instance_id` / `node_id` / `error_message` 占位（单花括号 `.format()` 渲染）
- [x] `workflow_tasks.py` 失败分支调用 `NotificationService.send_business`（通过 `_notify_workflow_failure` 辅助函数）
- [x] 通知接收人为 `instance.user_id`（对应 spec 中的 `created_by`，实际字段名）
- [x] 通知调用异常时仅记 warning，不影响终态写入和 SSE 推送
- [x] 新增失败通知触发单测（`test_workflow_failure_notification.py` 11 个测试）
- [x] `pytest tests/test_workflow*.py` 通过

## 阶段 4：标注沉浸式队列（#5）
- [x] `annotation-drawer.vue` 接收 `caseResults` 数组 + `initialIndex` props
- [x] 底部展示「上一条 / 下一条 (索引/总数)」按钮
- [x] 切换索引时正确加载上下文 + 重置表单 + 回显已有标注（watch currentIndex 触发 loadExisting）
- [x] 键盘快捷键：`P`=Pass、`F`=Fail、`J`/`→`=下一条、`K`/`←`=上一条、`Enter`=提交并下一条
- [x] 焦点在 input/textarea 时单字母快捷键不触发
- [x] 提交后自动跳下一条；最后一条提示并关闭（`submitAndNext`）
- [x] 保留原 `caseResultId` + `context` 单条模式兼容
- [x] `run.vue` 透传筛选后用例结果数组与索引（`detail.cases` 作为队列源）
- [x] `npm run type-check` 通过

## 阶段 5：验证
- [x] `pytest tests/test_workflow_*.py` 通过（45/45）
- [ ] `pytest tests/test_framework_alignment.py` 通过 — 8 个失败均为 PostgreSQL 连接错误（环境问题，与改动无关）
- [x] `pytest tests/test_workflow_annotation.py` 通过
- [x] `npm run type-check` 通过
- [x] 新增的失败节点透传单测通过
- [x] 新增的失败通知触发单测通过
